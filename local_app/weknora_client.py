"""Small, fail-closed WeKnora retrieval adapter for the training application.

The browser never receives the WeKnora API key.  The adapter intentionally
uses only ``POST /api/v1/knowledge-search`` and validates that every returned
chunk belongs to the configured knowledge-base allow-list.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


class WeKnoraSearchError(RuntimeError):
    """Raised when the configured WeKnora retrieval path is not trustworthy."""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise WeKnoraSearchError(f"{name} 必须是明确的布尔值")


def _split_ids(value: str) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for item in value.replace(";", ",").split(","):
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return tuple(result)


@dataclass(frozen=True)
class WeKnoraConfig:
    base_url: str
    api_key: str
    knowledge_base_ids: tuple[str, ...]
    timeout: float = 30.0
    required: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.knowledge_base_ids)

    @classmethod
    def from_env(cls) -> "WeKnoraConfig":
        base_url = os.getenv("WEKNORA_BASE_URL", "").strip().rstrip("/")
        if base_url.endswith("/api/v1"):
            base_url = base_url[: -len("/api/v1")]
        try:
            timeout = float(os.getenv("WEKNORA_TIMEOUT", "30"))
        except ValueError as exc:
            raise WeKnoraSearchError("WEKNORA_TIMEOUT 必须是数字") from exc
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 120:
            raise WeKnoraSearchError("WEKNORA_TIMEOUT 必须在 0 到 120 秒之间")
        return cls(
            base_url=base_url,
            api_key=os.getenv("WEKNORA_RETRIEVE_API_KEY", "").strip(),
            knowledge_base_ids=_split_ids(os.getenv("WEKNORA_KB_IDS", "")),
            timeout=timeout,
            required=_env_bool("WEKNORA_REQUIRED"),
        )


class WeKnoraSearchClient:
    def __init__(self, config: WeKnoraConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> "WeKnoraSearchClient":
        return cls(WeKnoraConfig.from_env())

    @property
    def configured(self) -> bool:
        return self.config.configured

    def configuration_error(self) -> str | None:
        if self.config.configured:
            return None
        missing: list[str] = []
        if not self.config.base_url:
            missing.append("WEKNORA_BASE_URL")
        if not self.config.api_key:
            missing.append("WEKNORA_RETRIEVE_API_KEY")
        if not self.config.knowledge_base_ids:
            missing.append("WEKNORA_KB_IDS")
        return "、".join(missing)

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        if not self.config.configured:
            raise WeKnoraSearchError(
                f"WeKnora 检索配置不完整：{self.configuration_error() or '未知配置'}"
            )
        payload = {
            "query": query,
            "knowledge_base_ids": list(self.config.knowledge_base_ids),
        }
        request = urllib.request.Request(
            f"{self.config.base_url}/api/v1/knowledge-search",
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "X-API-Key": self.config.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise WeKnoraSearchError(f"WeKnora 检索返回 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise WeKnoraSearchError(f"无法连接 WeKnora：{exc.reason}") from exc
        except TimeoutError as exc:
            raise WeKnoraSearchError("WeKnora 检索超时") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WeKnoraSearchError("WeKnora 返回了无法解析的数据") from exc
        if not isinstance(envelope, dict) or envelope.get("success") is not True:
            raise WeKnoraSearchError("WeKnora 返回的成功信封无效")
        rows = envelope.get("data")
        if not isinstance(rows, list):
            raise WeKnoraSearchError("WeKnora 检索结果不是列表")

        allowed = set(self.config.knowledge_base_ids)
        documents: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise WeKnoraSearchError("WeKnora 检索结果包含非对象记录")
            knowledge_base_id = str(row.get("knowledge_base_id") or "").strip()
            if not knowledge_base_id or knowledge_base_id not in allowed:
                raise WeKnoraSearchError("WeKnora 检索结果越出知识库白名单")
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            metadata = self._metadata(row)
            metadata.setdefault("title", str(row.get("knowledge_title") or "企业培训知识"))
            metadata.setdefault("knowledge_base_id", knowledge_base_id)
            # Chunk type is an authoritative server field; user-authored
            # metadata must not be able to disguise a text chunk as an FAQ.
            metadata["doc_type"] = self._doc_type(row, metadata)
            metadata.setdefault("domain", "safety" if metadata["doc_type"] == "safety" else "")
            # Imported FAQ metadata is user-authored.  It must not be able to
            # forge a local document/course citation or matched question.
            metadata.pop("matched_question", None)
            if metadata["doc_type"] == "common_qa":
                for key in ("document_id", "course_id", "module_id", "domain", "source_id", "chapter"):
                    metadata.pop(key, None)
                metadata["title"] = "顾客常见问题"
            document_id = str(
                metadata.get("document_id")
                or metadata.get("course_id")
                or row.get("knowledge_id")
                or row.get("id")
                or ""
            )
            try:
                numeric_score = float(row.get("score") or 0)
                score = round(numeric_score, 4) if math.isfinite(numeric_score) else 0.0
            except (TypeError, ValueError):
                score = 0.0
            # Validate every returned row, including rows after the caller's
            # display limit, so a malicious or mis-scoped tail record cannot
            # hide behind an otherwise valid first page.
            faq_answers = self._faq_answers(row, content) if metadata["doc_type"] == "common_qa" else []
            faq_questions = self._faq_questions(row, content) if metadata["doc_type"] == "common_qa" else []
            if metadata["doc_type"] == "common_qa" and not faq_answers:
                # Never expose an unrecognised FAQ transport wrapper or use it
                # for a direct answer.  A malformed FAQ hit is ignored.
                continue
            document_text = "\n".join(faq_answers) if faq_answers else content
            if len(documents) < max(1, limit):
                documents.append(
                    {
                        "document_id": document_id,
                        "text": document_text,
                        "metadata": metadata,
                        "retrieval_score": score,
                        "weknora": {
                            "chunk_id": str(row.get("id") or ""),
                            "knowledge_id": str(row.get("knowledge_id") or ""),
                            "knowledge_base_id": knowledge_base_id,
                            "match_type": str(row.get("match_type") or ""),
                            "chunk_type": str(row.get("chunk_type") or ""),
                            "faq_answers": faq_answers,
                            "faq_questions": faq_questions,
                        },
                    }
                )
        return documents

    @staticmethod
    def _metadata(row: Mapping[str, Any]) -> dict[str, str]:
        value = row.get("metadata")
        if not isinstance(value, dict):
            return {}
        return {
            str(key): str(item)
            for key, item in value.items()
            if key is not None and item is not None
        }

    @staticmethod
    def _doc_type(row: Mapping[str, Any], metadata: Mapping[str, str]) -> str:
        if str(row.get("chunk_type") or "").lower() == "faq":
            return "common_qa"
        document_id = str(metadata.get("document_id") or "")
        if document_id.startswith("SAFETY-"):
            return "safety"
        if metadata.get("course_id") or document_id.startswith("COURSE-"):
            return "course_section"
        return "knowledge"

    @staticmethod
    def _faq_answers(row: Mapping[str, Any], content: str) -> list[str]:
        """Read official FAQ answers, with a conservative v0.7.2 text fallback."""
        chunk_metadata = row.get("chunk_metadata")
        if isinstance(chunk_metadata, dict):
            answers = chunk_metadata.get("answers")
            if isinstance(answers, list):
                cleaned = [item.strip() for item in answers if isinstance(item, str) and item.strip()]
                if cleaned:
                    return cleaned
        marker = "\nAnswer:\n"
        if marker not in content:
            return []
        answer = content.split(marker, 1)[1]
        cleaned = [
            re.sub(r"^-\s+", "", line).strip()
            for line in answer.splitlines()
            if line.strip()
        ]
        return [item for item in cleaned if item]

    @staticmethod
    def _faq_questions(row: Mapping[str, Any], content: str) -> list[str]:
        """Read FAQ questions from server-owned structured chunk metadata."""
        chunk_metadata = row.get("chunk_metadata")
        questions: list[str] = []
        if isinstance(chunk_metadata, dict):
            standard = chunk_metadata.get("standard_question")
            if isinstance(standard, str) and standard.strip():
                questions.append(standard.strip())
            similar = chunk_metadata.get("similar_questions")
            if isinstance(similar, list):
                questions.extend(item.strip() for item in similar if isinstance(item, str) and item.strip())
        if not questions and content.startswith("Q:") and "\nAnswer:\n" in content:
            question = content[2:].split("\nAnswer:\n", 1)[0].strip()
            if question:
                questions.append(question)
        return list(dict.fromkeys(questions))
