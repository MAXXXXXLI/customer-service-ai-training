#!/usr/bin/env python3
"""Build a deterministic, governance-aware WeKnora migration bundle.

The source project contains several deliberate duplicates (course cards and RAG
documents repeat the current course text).  This builder preserves every source
file in an audit snapshot while emitting only one searchable copy of each
current course.  Customer-safe, safety-only, missing-material, historical, and
review-pending content are physically separated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET


MIGRATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MIGRATION_DIR.parent
KB_DIR = PROJECT_ROOT / "knowledge_base"
DEFAULT_OUTPUT = MIGRATION_DIR / "bundle"
GENERATOR_MARKER = ".generated-by-build_bundle"
BUNDLE_VERSION = "2026-08-27-weknora-v6"

BLOCKED_POINT_WAVE_FAQ_ID = "FAQ-XLS-0002"
BLOCKED_POINT_WAVE_EXTERNAL_ID = "FAQ-XLS-0002"

TAXONOMY_DOCX = "秀域与春语两大知识体系_四级标题纲要_2026年8月.docx"
SECONDARY_TAXONOMY_DOCX = "秀域十大知识板块_三级标题纲要_2026年8月.docx"
CURRENT_SOURCE_ID = "NKB-2026-08-HIGH-DENSITY"
SRC035_ORIGINAL_NAME = "1786691706191.xls"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=False) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_slug(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip())
    return value.strip("-") or "document"


def course_line_ranges(
    source: Path,
    courses: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, int]]:
    """Map every catalog course to its exact 1-based range in the authority Markdown."""
    lines = source.read_text(encoding="utf-8").splitlines()
    starts: List[Tuple[str, int]] = []
    for course in courses:
        heading = f"## {course['title']}"
        matches = [index for index, line in enumerate(lines, 1) if line.strip() == heading]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one authority heading for {course['id']}/{course['title']}, got {matches}"
            )
        starts.append((str(course["id"]), matches[0]))
    result: Dict[str, Dict[str, int]] = {}
    for course_id, start in starts:
        next_boundary = next(
            (
                index
                for index, line in enumerate(lines[start:], start + 1)
                if re.match(r"^#{1,2}\s+", line)
            ),
            len(lines) + 1,
        )
        end = next_boundary - 1
        result[course_id] = {"line_start": start, "line_end": end}
    return result


def string_metadata(**values: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, (list, dict, tuple, bool, int, float)):
            result[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            result[key] = str(value)
    return result


def bullets(values: Sequence[Any], fallback: str = "- 无") -> str:
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return "\n".join(f"- {item}" for item in cleaned) if cleaned else fallback


def numbered(values: Sequence[Any], fallback: str = "1. 无") -> str:
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    return "\n".join(f"{index}. {item}" for index, item in enumerate(cleaned, 1)) if cleaned else fallback


def parse_docx_paragraphs(path: Path) -> List[Tuple[str, str]]:
    """Read paragraph style and text from a DOCX using only the stdlib."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    rows: List[Tuple[str, str]] = []
    for paragraph in root.findall(".//w:body/w:p", NS):
        style_node = paragraph.find("./w:pPr/w:pStyle", NS)
        style = style_node.get(f"{{{W_NS}}}val", "") if style_node is not None else ""
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
        if text:
            rows.append((style, text))
    return rows


def build_taxonomy(docx_path: Path) -> Dict[str, Any]:
    current_system = ""
    current_module = ""
    current_course: Optional[MutableMapping[str, Any]] = None
    systems: List[Dict[str, Any]] = []
    modules: List[Dict[str, Any]] = []
    courses: List[Dict[str, Any]] = []
    system_map: Dict[str, Dict[str, Any]] = {}

    for style, text in parse_docx_paragraphs(docx_path):
        if style == "Heading1":
            current_system = text.split("｜", 1)[-1].strip()
            if current_system not in system_map:
                entry = {"name": current_system, "modules": []}
                system_map[current_system] = entry
                systems.append(entry)
        elif style == "Heading2":
            current_module = text
            module_no_match = re.search(r"板块([一二三四五六七八九十]+)", text)
            module_entry = {
                "title": text,
                "system": current_system,
                "ordinal_cn": module_no_match.group(1) if module_no_match else "",
                "courses": [],
            }
            modules.append(module_entry)
            if current_system:
                system_map[current_system]["modules"].append(text)
        elif style == "Heading3":
            match = re.match(r"(\d+)\.(\d+)\s+(.*)", text)
            if not match:
                continue
            current_course = {
                "module_number": int(match.group(1)),
                "course_number_in_module": int(match.group(2)),
                "code": f"{match.group(1)}.{match.group(2)}",
                "title": match.group(3).strip(),
                "system": current_system,
                "module_title": current_module,
                "leaf_titles": [],
            }
            courses.append(dict(current_course))
            if modules:
                modules[-1]["courses"].append(current_course["code"])
        elif style == "Heading4" and current_course is not None:
            match = re.match(r"(\d+\.\d+\.\d+)\s+(.*)", text)
            leaf = {
                "code": match.group(1) if match else "",
                "title": match.group(2).strip() if match else text,
            }
            courses[-1]["leaf_titles"].append(leaf)

    return {
        "source_file": docx_path.name,
        "systems": systems,
        "modules": modules,
        "courses": courses,
        "counts": {
            "systems": len(systems),
            "modules": len(modules),
            "courses": len(courses),
            "leaf_titles": sum(len(course["leaf_titles"]) for course in courses),
        },
    }


def taxonomy_markdown(taxonomy: Mapping[str, Any]) -> str:
    lines = [
        "# 秀域与春语知识分类目录",
        "",
        "> 本文档只定义分类和导航，不增加项目事实，不作为顾客答案来源。",
        "",
    ]
    for system in taxonomy["systems"]:
        lines.extend([f"## {system['name']}", ""])
        for module in [m for m in taxonomy["modules"] if m["system"] == system["name"]]:
            lines.extend([f"### {module['title']}", ""])
            codes = set(module["courses"])
            for course in [c for c in taxonomy["courses"] if c["code"] in codes]:
                lines.extend([f"#### {course['code']} {course['title']}", ""])
                for leaf in course["leaf_titles"]:
                    lines.append(f"- {leaf['code']} {leaf['title']}")
                lines.append("")
    return "\n".join(lines)


def course_markdown(
    course: Mapping[str, Any],
    card: Mapping[str, Any],
    module: Mapping[str, Any],
    taxonomy_course: Optional[Mapping[str, Any]],
) -> str:
    system = "春语" if course["module_id"] in {"MOD-09", "MOD-10"} else "秀域"
    lines = [
        f"# {course['title']}",
        "",
        "> 用途：员工学习与内部检索。顾客沟通必须同时执行安全知识库和确定性规则。",
        "",
        "## 治理信息",
        "",
        f"- 知识体系：{system}",
        f"- 模块：{course['module_id']}｜{module['title']}",
        f"- 课程 ID：{course['id']}",
        f"- 当前状态：current_internal_course",
        f"- 权威来源：{course.get('authority', '')}",
        f"- 来源 ID：{'、'.join(course.get('source_ids', []))}",
        "- 顾客智能体权限：禁止直接绑定",
        "- 结构核验：2026-08-19 已通过",
        "- 事实核验：涉及医疗、药品、设备、疗效和动态信息时仍需当前批准材料",
        "",
        "## 课程摘要",
        "",
        str(course.get("summary", "")).strip(),
        "",
    ]
    for section in course.get("sections", []):
        lines.extend([f"## {section['title']}", ""])
        for paragraph in section.get("content", []):
            lines.extend([str(paragraph).strip(), ""])

    lines.extend(
        [
            "## 必须执行",
            "",
            bullets(card.get("required_actions", [])),
            "",
            "## 推荐表达",
            "",
            bullets(card.get("recommended_language", [])),
            "",
            "## 禁止表达",
            "",
            bullets(card.get("bad_patterns", [])),
            "",
            "## 训练问题",
            "",
            numbered(card.get("question_bank", [])),
            "",
            "## 训练与考核重点",
            "",
            f"训练重点：{'；'.join(card.get('training_focus', [])) or '无'}",
            "",
            f"考核重点：{'；'.join(card.get('testing_focus', [])) or '无'}",
            "",
        ]
    )
    if taxonomy_course:
        lines.extend(
            [
                "## 分类叶标题（导航，不代表新增事实）",
                "",
                *[
                    f"- {leaf['code']} {leaf['title']}"
                    for leaf in taxonomy_course.get("leaf_titles", [])
                ],
                "",
            ]
        )
    return "\n".join(lines)


def objection_markdown(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# 员工异议处理训练",
        "",
        "> 仅供员工训练。价格、活动和效果类信息必须核验当前生效版本。OB-001 的过期促销话术已隔离。",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['id']}｜{row['trigger']}",
                "",
                f"安全处理：{row.get('safe_handling', '')}",
                "",
                f"推荐表达：{row.get('recommended_language', '')}",
                "",
                f"来源：{'、'.join(row.get('source_ids', [])) or '未登记'}",
                "",
            ]
        )
    return "\n".join(lines)


def build_customer_faq(
    current_rows: Sequence[Mapping[str, Any]],
    historical_rows: Sequence[Mapping[str, Any]],
    authority_ranges: Mapping[str, Mapping[str, int]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    entries: List[Dict[str, Any]] = []
    metadata_rows: List[Dict[str, Any]] = []
    for row in current_rows:
        aliases = []
        seen = {row["question"].strip()}
        for alias in row.get("question_aliases", []):
            alias = str(alias).strip()
            if alias and alias not in seen:
                aliases.append(alias)
                seen.add(alias)
        high_risk = row.get("risk_level") == "高"
        course_id = str(row.get("mapped_course_id", ""))
        source_range = authority_ranges.get(course_id, {})
        faq_entry = {
            "standard_question": row["question"].strip(),
            "similar_questions": aliases,
            "negative_questions": [],
            "answers": [row["approved_answer"].strip()],
            "answer_strategy": "all",
            "tag_name": f"{row['module_id']}-current",
            "is_enabled": False,
            "is_recommended": False,
        }
        entries.append(faq_entry)
        metadata_rows.append(
            {
                "external_id": row["id"],
                "standard_question": row["question"],
                "source_id": row.get("source_id"),
                "source_record_indices": row.get("source_rows", []),
                "source_line_start": source_range.get("line_start"),
                "source_line_end": source_range.get("line_end"),
                "module_id": row.get("module_id"),
                "course_id": course_id,
                "risk_level": row.get("risk_level"),
                "authority_level": "current_integrated_course_answer",
                "answer_status": "review_required" if high_risk else "provisional_current",
                "customer_rag_allowed": False,
                "review_owner": "unassigned",
                "last_verified_at": None,
                "effective_from": row.get("last_modified"),
                "expires_on": None,
                "supersedes": [],
                "content_sha256": json_sha256(faq_entry),
            }
        )

    covered = [row for row in historical_rows if row.get("status") == "covered"]
    blocked_rows = [row for row in covered if row.get("id") == BLOCKED_POINT_WAVE_FAQ_ID]
    if len(blocked_rows) != 1:
        raise RuntimeError(
            f"Expected exactly one {BLOCKED_POINT_WAVE_FAQ_ID} historical FAQ, "
            f"got {len(blocked_rows)}"
        )

    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in covered:
        if row.get("id") == BLOCKED_POINT_WAVE_FAQ_ID:
            continue
        grouped[row["approved_answer"].strip()].append(row)

    grouped_rows: List[Tuple[str, str, List[Mapping[str, Any]], bool]] = [
        (
            BLOCKED_POINT_WAVE_EXTERNAL_ID,
            str(blocked_rows[0]["approved_answer"]).strip(),
            blocked_rows,
            True,
        )
    ]
    grouped_rows.extend(
        (
            f"FAQ-LEGACY-GROUP-{group_no:02d}",
            answer,
            rows,
            False,
        )
        for group_no, (answer, rows) in enumerate(
            sorted(grouped.items(), key=lambda item: min(row["id"] for row in item[1])),
            1,
        )
    )

    topic_modules = {
        "point_wave": "MOD-03",
        "point_wave_aftercare": "MOD-03",
        "super_v": "MOD-04",
    }
    for external_id, answer, rows, publication_blocked in grouped_rows:
        questions = []
        for row in rows:
            for value in [row["question"], *row.get("question_aliases", [])]:
                question = str(value).strip()
                if question and question not in questions:
                    questions.append(question)
        source_topics = sorted({row.get("topic", "") for row in rows if row.get("topic")})
        current_modules = sorted(
            {
                topic_modules.get(str(row.get("topic", "")), str(row.get("module_id", "")))
                for row in rows
                if topic_modules.get(str(row.get("topic", "")), str(row.get("module_id", "")))
            }
        )
        faq_entry = {
            "standard_question": questions[0],
            "similar_questions": questions[1:],
            "negative_questions": [],
            "answers": [answer],
            "answer_strategy": "all",
            "tag_name": (
                "business-proposed-exception-blocked"
                if publication_blocked
                else "legacy-covered-review-required"
            ),
            "is_enabled": False,
            "is_recommended": False,
        }
        entries.append(faq_entry)
        metadata_rows.append(
            {
                "external_id": external_id,
                "standard_question": questions[0],
                "source_ids": sorted({row.get("source_id") for row in rows if row.get("source_id")}),
                "source_rows": sorted({n for row in rows for n in row.get("source_rows", [])}),
                "original_question_ids": [row["id"] for row in rows],
                "question_count": len(questions),
                "topics": source_topics,
                "module_ids": current_modules,
                "authority_level": (
                    "business_proposed_exception"
                    if publication_blocked
                    else "historical_question_current_safe_rewrite"
                ),
                "answer_status": (
                    "blocked_pending_safety_review"
                    if publication_blocked
                    else "review_required"
                ),
                "risk_level": "高" if publication_blocked else None,
                "secondary_review_required": publication_blocked,
                "publication_blocked": publication_blocked,
                "customer_rag_allowed": False,
                "review_owner": "unassigned",
                "last_verified_at": None,
                "effective_from": None,
                "expires_on": None,
                "supersedes": [],
                "content_sha256": json_sha256(faq_entry),
            }
        )
    return entries, metadata_rows


def safety_governance_markdown(
    compliance: Mapping[str, Any],
    methodology: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> str:
    lines = [
        "# 顾客回答安全规范与路由方法",
        "",
        "> 本知识用于解释和引用；实际调用必须先后执行应用层确定性安全闸门，不得仅依赖向量检索或提示词。",
        "",
        "## 统一合规规则",
        "",
    ]
    for rule in compliance.get("rules", []):
        lines.extend([f"### {rule['id']}｜{rule['title']}", "", bullets(rule.get("requirements", [])), ""])
    lines.extend(["## 核心原则", "", bullets(methodology.get("core_principles", [])), ""])
    lines.extend(["## 服务流程", ""])
    for item in methodology.get("service_flow", []):
        lines.append(f"{item['step']}. **{item['name']}**：{item['goal']}")
    lines.extend(["", "## 回答执行顺序", ""])
    for item in methodology.get("answer_execution_order", []):
        lines.append(f"{item['order']}. **{item['name']}**：{item['instruction']}")
    lines.extend(["", "## 业务主题路由", ""])
    for route in methodology.get("topic_routes", []):
        lines.extend(
            [
                f"### {route['id']}｜{route['label']}",
                "",
                f"主模块：{route.get('module_id', '')}",
                "",
                f"识别词：{'；'.join(route.get('patterns', []))}",
                "",
                f"下一步：{route.get('recommended_next', '')}",
                "",
            ]
        )
    lines.extend(["## 意图优先级与安全覆盖", ""])
    for route in sorted(methodology.get("intent_routes", []), key=lambda row: -row.get("priority", 0)):
        lines.extend(
            [
                f"### {route['id']}｜{route['label']}（优先级 {route.get('priority', 0)}）",
                "",
                f"处理重点：{route.get('focus', '')}",
                "",
                f"推荐下一步：{route.get('recommended_next', '')}",
                "",
                f"是否停止销售推进：{'是' if route.get('stop_sales') else '否'}",
                "",
                f"识别模式：{'；'.join(route.get('patterns', []))}",
                "",
            ]
        )
    lines.extend(["## 关键失败规则", ""])
    for item in rubric.get("critical_failures", []):
        lines.append(f"- {item['code']}：{item['rule']}（得分上限 {item['score_cap']}）")
    lines.extend(["", "## 标准回答模板", ""])
    for key, value in methodology.get("answer_template", {}).items():
        lines.append(f"- {key}：{value}")
    return "\n".join(lines)


def build_boundary_faq(
    rows: Sequence[Mapping[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Collapse historical boundary-only questions into deterministic FAQ groups."""
    boundary = [row for row in rows if row.get("status") == "boundary_only"]
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in boundary:
        grouped[row["approved_answer"].strip()].append(row)

    entries: List[Dict[str, Any]] = []
    metadata_rows: List[Dict[str, Any]] = []
    for number, (answer, items) in enumerate(
        sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])), 1
    ):
        questions = sorted({item["question"].strip() for item in items})
        topics = sorted({item.get("topic", "") for item in items if item.get("topic")})
        external_id = f"SAFETY-BOUNDARY-{number:02d}"
        faq_entry = {
            "standard_question": questions[0],
            "similar_questions": questions[1:],
            "negative_questions": [],
            "answers": [answer],
            "answer_strategy": "all",
            "tag_name": "safety-boundary",
            "is_enabled": False,
            "is_recommended": False,
        }
        entries.append(faq_entry)
        metadata_rows.append(
            {
                "external_id": external_id,
                "standard_question": questions[0],
                "original_question_ids": sorted(item["id"] for item in items),
                "question_count": len(questions),
                "topics": topics,
                "source_ids": sorted({item.get("source_id") for item in items if item.get("source_id")}),
                "source_rows": sorted({n for item in items for n in item.get("source_rows", [])}),
                "authority_level": "deterministic_boundary_rewrite",
                "answer_status": "review_required_boundary_only",
                "customer_rag_allowed": False,
                "review_owner": "unassigned",
                "last_verified_at": None,
                "effective_from": None,
                "expires_on": None,
                "supersedes": [],
                "content_sha256": json_sha256(faq_entry),
            }
        )
    return entries, metadata_rows


def approval_template(metadata_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "external_id": row["external_id"],
            "content_sha256": row["content_sha256"],
            "decision": "pending",
            "review_owner": "",
            "secondary_review_owner": "",
            "last_verified_at": "",
            "effective_from": "",
            "expires_on": "",
            "notes": "",
        }
        for row in metadata_rows
    ]


def audit_markdown(source: Path, display_name: str, authority: str = "audit_only") -> str:
    banner = [
        f"# 审计留档｜{display_name}",
        "",
        "> 仅供管理员和审核人员追溯。不得绑定顾客智能体；其中的医学、设备、药品、疗效和动态信息不代表已完成事实核验。",
        "",
        f"- 原文件：{display_name}",
        f"- SHA-256：{sha256(source)}",
        f"- 权威级别：{authority}",
        "",
        "---",
        "",
    ]
    if source.suffix.lower() == ".md":
        body = source.read_text(encoding="utf-8", errors="replace")
    else:
        language = "jsonl" if source.suffix.lower() == ".jsonl" else "json"
        body = f"```{language}\n{source.read_text(encoding='utf-8', errors='replace').rstrip()}\n```"
    return "\n".join(banner) + body


def audit_docx_markdown(source: Path) -> str:
    lines = [
        f"# 审计留档｜{source.name}",
        "",
        "> 仅供管理员和审核人员追溯。本 DOCX 只提供分类标题，不增加项目事实。",
        "",
        f"- 原文件：{source.name}",
        f"- SHA-256：{sha256(source)}",
        "- 权威级别：taxonomy_only",
        "",
        "## 标题抽取",
        "",
    ]
    for style, text in parse_docx_paragraphs(source):
        lines.append(f"- [{style or 'Normal'}] {text}")
    return "\n".join(lines)


def external_source_root() -> Optional[Path]:
    """Return an optional portable directory containing the four external inputs."""

    configured = os.environ.get("WEKNORA_SOURCE_INPUT_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else None


def find_handoff_archive(search_root: Path) -> Optional[Path]:
    candidates = sorted(search_root.glob("customer-service-ai-training-handoff-final-*.zip"))
    return candidates[-1] if candidates else None


def extract_historical_raw_sources(archive_path: Path, destination: Path) -> List[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: List[Path] = []
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            prefix = "knowledge_base/raw_sources/"
            if info.is_dir() or not normalized.startswith(prefix):
                continue
            relative = normalized[len(prefix) :]
            if not relative or Path(relative).suffix.lower() not in {".md", ".jsonl"}:
                continue
            target = destination / Path(relative).name
            target.write_bytes(archive.read(info))
            extracted.append(target)
    return sorted(extracted)


def add_document_manifest(
    rows: List[Dict[str, Any]],
    bundle_root: Path,
    path: Path,
    title: str,
    metadata: Mapping[str, str],
) -> None:
    rows.append(
        {
            "path": path.relative_to(bundle_root).as_posix(),
            "title": title,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "metadata": dict(metadata),
        }
    )


def copy_snapshot(
    source: Path,
    destination: Path,
    snapshot_rows: List[Dict[str, Any]],
    origin: str,
    bundle_root: Path,
    source_label: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    snapshot_rows.append(
        {
            "path": destination.relative_to(bundle_root).as_posix(),
            "origin": origin,
            "source_path": source_label,
            "sha256": sha256(destination),
            "size_bytes": destination.stat().st_size,
        }
    )


def build_bundle(output: Path) -> Dict[str, Any]:
    config = read_json(MIGRATION_DIR / "config.json")
    # v5 is pinned in the generator so deployments cannot silently reuse v4
    # state or approval receipts after the governed FAQ content changed.
    config["bundle_version"] = BUNDLE_VERSION
    portable_sources = external_source_root()
    taxonomy_root = portable_sources or PROJECT_ROOT.parent
    if output.exists():
        marker = output / GENERATOR_MARKER
        if not marker.exists():
            raise RuntimeError(f"Refusing to replace unmarked directory: {output}")
        shutil.rmtree(output)

    stage_parent = output.parent
    stage_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bundle-stage-", dir=stage_parent) as temp_dir:
        stage = Path(temp_dir)
        (stage / GENERATOR_MARKER).write_text("generated; safe to rebuild\n", encoding="utf-8")

        learning_catalog = read_json(KB_DIR / "learning_catalog.json")
        learning_modules = read_json(KB_DIR / "learning_modules.json")
        cards = read_jsonl(KB_DIR / "knowledge_cards.jsonl")
        current_faq = read_jsonl(KB_DIR / "common_qa_catalog.jsonl")
        historical_faq = read_jsonl(KB_DIR / "common_qa_excel_catalog.jsonl")
        rag_documents = read_jsonl(KB_DIR / "rag_documents.jsonl")
        objections = read_jsonl(KB_DIR / "objection_library.jsonl")
        compliance = read_json(KB_DIR / "compliance_references.json")
        methodology = read_json(KB_DIR / "customer_service_methodology.json")
        rubric = read_json(KB_DIR / "scoring_rubric.json")
        video_review = read_jsonl(KB_DIR / "video_knowledge_review_queue.jsonl")
        source_registry = read_json(KB_DIR / "source_registry.json")
        authority_source = KB_DIR / "秀域企业完整知识库_高密度整合版_2026年8月.md"
        authority_ranges = course_line_ranges(authority_source, learning_catalog["courses"])
        source_registry_extension = {
            "schema_version": 1,
            "source_id": CURRENT_SOURCE_ID,
            "title": "秀域企业完整知识库｜高密度整合版｜2026年8月",
            "relative_path": "knowledge_base/秀域企业完整知识库_高密度整合版_2026年8月.md",
            "sha256": sha256(authority_source),
            "version": config["source_version"],
            "authority_level": "current_course_authority",
            "status": "available_in_current_workspace",
            "note": "补充旧 source_registry.json 的缺失登记；不修改原始治理文件。",
        }
        write_json(stage / "source_registry_extension.json", source_registry_extension)

        taxonomy_path = taxonomy_root / TAXONOMY_DOCX
        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Required taxonomy DOCX not found: {taxonomy_path}")
        taxonomy = build_taxonomy(taxonomy_path)
        write_json(stage / "taxonomy.json", taxonomy)

        module_by_id = {row["id"]: row for row in learning_modules["modules"]}
        card_by_course = {row["course_id"]: row for row in cards}
        taxonomy_by_title = {row["title"]: row for row in taxonomy["courses"]}

        manifests: Dict[str, List[Dict[str, Any]]] = {
            "staff_courses": [],
            "safety_policy": [],
            "audit_raw": [],
        }

        staff_dir = stage / "staff_courses"
        for course in learning_catalog["courses"]:
            card = card_by_course[course["id"]]
            module = module_by_id[course["module_id"]]
            taxonomy_course = taxonomy_by_title.get(course["title"])
            path = staff_dir / f"{course['id']}-{safe_slug(course['title'])}.md"
            write_text(path, course_markdown(course, card, module, taxonomy_course))
            add_document_manifest(
                manifests["staff_courses"],
                stage,
                path,
                course["title"],
                string_metadata(
                    document_id=course["id"],
                    system="春语" if course["module_id"] in {"MOD-09", "MOD-10"} else "秀域",
                    module_id=course["module_id"],
                    module_title=module["title"],
                    course_id=course["id"],
                    source_id=CURRENT_SOURCE_ID,
                    version=config["source_version"],
                    authority_level="current_internal_course",
                    answer_status="current",
                    customer_rag_allowed=False,
                    risk_level="mixed_review_required",
                    review_owner="unassigned",
                    effective_from="2026-08-19",
                    expires_on=None,
                    source_line_start=authority_ranges[course["id"]]["line_start"],
                    source_line_end=authority_ranges[course["id"]]["line_end"],
                ),
            )

        safe_objections = [row for row in objections if row["id"] != "OB-001"]
        objection_path = staff_dir / "STAFF-OBJECTION-HANDLING.md"
        write_text(objection_path, objection_markdown(safe_objections))
        add_document_manifest(
            manifests["staff_courses"], stage, objection_path, "员工异议处理训练",
            string_metadata(
                document_id="STAFF-OBJECTION-HANDLING",
                authority_level="staff_training",
                customer_rag_allowed=False,
                version=config["source_version"],
                excluded_ids=["OB-001"],
            ),
        )
        taxonomy_md_path = staff_dir / "STAFF-TAXONOMY.md"
        write_text(taxonomy_md_path, taxonomy_markdown(taxonomy))
        add_document_manifest(
            manifests["staff_courses"], stage, taxonomy_md_path, "秀域与春语知识分类目录",
            string_metadata(
                document_id="STAFF-TAXONOMY",
                authority_level="taxonomy_only",
                customer_rag_allowed=False,
                source_file=TAXONOMY_DOCX,
            ),
        )
        write_jsonl(staff_dir / "document_manifest.jsonl", manifests["staff_courses"])

        customer_entries, customer_metadata = build_customer_faq(
            current_faq,
            historical_faq,
            authority_ranges,
        )
        customer_dir = stage / "customer_approved"
        write_json(customer_dir / "faq_entries.json", customer_entries)
        write_json(
            customer_dir / "faq_batch.replace.json",
            {"mode": "replace", "dry_run": False, "entries": customer_entries},
        )
        write_jsonl(customer_dir / "faq_metadata.jsonl", customer_metadata)
        write_jsonl(
            customer_dir / "approval_template.jsonl",
            approval_template(customer_metadata),
        )
        write_text(
            customer_dir / "README.md",
            """# 顾客问答导入说明

- 43 条当前课程 FAQ 首次导入全部停用；结构验证不代表已获得顾客发布授权。
- 其中 38 条常规项与 5 条高风险项都必须填写审核人、核验时间和有效期；高风险项还需专业/合规复核。
- 历史 105 条 `covered` 主问题及其别名按答案折叠为 6 条 FAQ，默认停用待审。
- `FAQ-XLS-0002` 使用独立稳定 ID，携带 5 条相似问法；其业务建议话术与当前安全课程存在冲突，因此本版本阻止直接发布，只能留在待审库中追溯。
- `faq_metadata.jsonl` 保存 WeKnora FAQ 本身无法表达的治理字段。
- 536 条 `boundary_only` 不进入本库，已折叠进 `KB-SAFETY-BOUNDARY`。
- 390 条 `material_missing` 只进入审计库，任何智能体不得据此猜测答案。
""",
        )

        safety_dir = stage / "safety_policy"
        governance_path = safety_dir / "SAFETY-GOVERNANCE-AND-ROUTING.md"
        write_text(governance_path, safety_governance_markdown(compliance, methodology, rubric))
        add_document_manifest(
            manifests["safety_policy"], stage, governance_path, "顾客回答安全规范与路由方法",
            string_metadata(
                document_id="SAFETY-GOVERNANCE-AND-ROUTING",
                authority_level="enterprise_safety_policy",
                answer_status="staff_only_pending_named_review",
                customer_rag_allowed=False,
                source_ids=["compliance_references.json", "customer_service_methodology.json", "scoring_rubric.json"],
                version=config["source_version"],
                effective_from="2026-08-19",
                review_owner="unassigned",
                last_verified_at=None,
            ),
        )
        write_jsonl(safety_dir / "document_manifest.jsonl", manifests["safety_policy"])

        boundary_entries, boundary_metadata = build_boundary_faq(historical_faq)
        boundary_dir = stage / "safety_boundary"
        write_json(boundary_dir / "faq_entries.json", boundary_entries)
        write_json(
            boundary_dir / "faq_batch.replace.json",
            {"mode": "replace", "dry_run": False, "entries": boundary_entries},
        )
        write_jsonl(boundary_dir / "faq_metadata.jsonl", boundary_metadata)
        write_jsonl(
            boundary_dir / "approval_template.jsonl",
            approval_template(boundary_metadata),
        )
        write_text(
            boundary_dir / "README.md",
            """# 安全边界 FAQ 导入说明

- 536 条 `boundary_only` 历史问法按完全相同的边界答案折叠为 9 条 FAQ。
- 因缺少审核人和核验日期，9 组首次导入全部停用且不推荐；审核签字后再逐组启用。
- 本库不包含项目原理、剂量、参数、价格、疗程或效果补写。
- 应用层确定性安全闸门仍必须保留，不能用 FAQ 检索取代。
""",
        )

        snapshot_rows: List[Dict[str, Any]] = []
        snapshot_dir = stage / "source_snapshot"
        for source in sorted(path for path in KB_DIR.iterdir() if path.is_file()):
            destination = snapshot_dir / "knowledge_base" / source.name
            copy_snapshot(
                source,
                destination,
                snapshot_rows,
                "current_workspace",
                stage,
                f"project/knowledge_base/{source.name}",
            )
        copy_snapshot(
            PROJECT_ROOT / "manifest.json",
            snapshot_dir / "manifest.json",
            snapshot_rows,
            "current_workspace",
            stage,
            "project/manifest.json",
        )
        prompt_defaults = PROJECT_ROOT / "local_app" / "static" / "data" / "prompt_defaults.json"
        if prompt_defaults.exists():
            copy_snapshot(
                prompt_defaults,
                snapshot_dir / "local_app" / "prompt_defaults.json",
                snapshot_rows,
                "current_workspace",
                stage,
                "project/local_app/static/data/prompt_defaults.json",
            )
        for docx_name in [TAXONOMY_DOCX, SECONDARY_TAXONOMY_DOCX]:
            docx = taxonomy_root / docx_name
            if docx.exists():
                copy_snapshot(
                    docx,
                    snapshot_dir / "taxonomy" / docx.name,
                    snapshot_rows,
                    "workspace_taxonomy",
                    stage,
                    f"source_inputs/{docx.name}",
                )

        src035_original = (
            portable_sources / SRC035_ORIGINAL_NAME
            if portable_sources
            else Path.home() / "Downloads" / SRC035_ORIGINAL_NAME
        )
        if not src035_original.exists():
            raise FileNotFoundError(
                f"Required registered original SRC-035 not found: {src035_original}"
            )
        copy_snapshot(
            src035_original,
            snapshot_dir / "originals" / f"SRC-035-{SRC035_ORIGINAL_NAME}",
            snapshot_rows,
            "current_original",
            stage,
            f"source_inputs/{SRC035_ORIGINAL_NAME}",
        )

        handoff = find_handoff_archive(portable_sources or PROJECT_ROOT.parent)
        historical_raw_files: List[Path] = []
        if handoff:
            historical_raw_files = extract_historical_raw_sources(
                handoff, snapshot_dir / "historical_raw_sources"
            )
            for source in historical_raw_files:
                snapshot_rows.append(
                    {
                        "path": source.relative_to(stage).as_posix(),
                        "origin": "2026-08-15-handoff-archive",
                        "source_path": (
                            f"source_inputs/{handoff.name}!knowledge_base/raw_sources/{source.name}"
                        ),
                        "sha256": sha256(source),
                        "size_bytes": source.stat().st_size,
                    }
                )

        write_json(stage / "source_snapshot_manifest.json", snapshot_rows)

        audit_dir = stage / "audit_raw"
        current_snapshot_files = sorted((snapshot_dir / "knowledge_base").glob("*"))
        for source in current_snapshot_files:
            if source.suffix.lower() not in {".md", ".json", ".jsonl"}:
                continue
            path = audit_dir / f"AUDIT-CURRENT-{safe_slug(source.stem)}.md"
            write_text(path, audit_markdown(source, source.name, "current_workspace_audit"))
            add_document_manifest(
                manifests["audit_raw"], stage, path, f"审计留档｜{source.name}",
                string_metadata(
                    document_id=f"AUDIT-CURRENT-{safe_slug(source.stem)}",
                    authority_level="audit_only",
                    answer_status="not_for_answering",
                    customer_rag_allowed=False,
                    source_file=source.name,
                    source_sha256=sha256(source),
                ),
            )
        for source, display_name in [
            (snapshot_dir / "manifest.json", "manifest.json"),
            (snapshot_dir / "local_app" / "prompt_defaults.json", "prompt_defaults.json"),
            (stage / "source_snapshot_manifest.json", "source_snapshot_manifest.json"),
            (stage / "source_registry_extension.json", "source_registry_extension.json"),
        ]:
            if not source.exists():
                continue
            path = audit_dir / f"AUDIT-GOVERNANCE-{safe_slug(source.stem)}.md"
            write_text(path, audit_markdown(source, display_name, "governance_snapshot"))
            add_document_manifest(
                manifests["audit_raw"], stage, path, f"治理留档｜{display_name}",
                string_metadata(
                    document_id=f"AUDIT-GOVERNANCE-{safe_slug(source.stem)}",
                    authority_level="governance_snapshot",
                    answer_status="not_for_answering",
                    customer_rag_allowed=False,
                    source_file=display_name,
                    source_sha256=sha256(source),
                ),
            )
        for docx_name in [TAXONOMY_DOCX, SECONDARY_TAXONOMY_DOCX]:
            source = snapshot_dir / "taxonomy" / docx_name
            if not source.exists():
                continue
            path = audit_dir / f"AUDIT-TAXONOMY-{safe_slug(source.stem)}.md"
            write_text(path, audit_docx_markdown(source))
            add_document_manifest(
                manifests["audit_raw"], stage, path, f"分类留档｜{docx_name}",
                string_metadata(
                    document_id=f"AUDIT-TAXONOMY-{safe_slug(source.stem)}",
                    authority_level="taxonomy_only",
                    answer_status="not_for_answering",
                    customer_rag_allowed=False,
                    source_file=docx_name,
                    source_sha256=sha256(source),
                ),
            )
        for source in historical_raw_files:
            if source.suffix.lower() != ".md":
                continue
            path = audit_dir / f"AUDIT-HISTORICAL-{safe_slug(source.stem)}.md"
            write_text(path, audit_markdown(source, source.name, "historical_extraction_review_only"))
            add_document_manifest(
                manifests["audit_raw"], stage, path, f"历史来源抽取｜{source.name}",
                string_metadata(
                    document_id=f"AUDIT-HISTORICAL-{safe_slug(source.stem)}",
                    authority_level="historical_extraction_review_only",
                    answer_status="review_required",
                    customer_rag_allowed=False,
                    source_file=source.name,
                    source_sha256=sha256(source),
                ),
            )
        governance_path = audit_dir / "AUDIT-MIGRATION-GOVERNANCE.md"
        registered_ids = {
            str(item.get("source_id"))
            for item in source_registry.get("sources", [])
            if item.get("source_id")
        }
        write_text(
            governance_path,
            "\n".join(
                [
                    "# 迁移治理记录",
                    "",
                    "> 仅供管理员和审核人员。本记录描述可追溯性边界，不是顾客答案。",
                    "",
                    f"- 当前课程权威源 ID：{CURRENT_SOURCE_ID}",
                    f"- 旧 source_registry.json 是否登记该 ID：{'yes' if CURRENT_SOURCE_ID in registered_ids else 'no'}",
                    "- 本迁移包 source_registry_extension.json 是否补充登记：yes",
                    f"- 旧登记来源数：{source_registry.get('source_count', len(registered_ids))}",
                    f"- 本迁移包有效来源数：{len(registered_ids | {CURRENT_SOURCE_ID})}",
                    f"- 权威源路径：{source_registry_extension['relative_path']}",
                    f"- 权威源 SHA256：{source_registry_extension['sha256']}",
                    f"- 从 2026-08-15 交付包恢复的历史抽取文件：{len(historical_raw_files)}",
                    "- 历史抽取稿只供追溯，不等于原 PPT/Word/PDF/MP4 已在当前工作区可重放。",
                    "- 43 条视频复核项均保持 pending_review 且排除于顾客 RAG。",
                    "- 390 条 material_missing 只留在审计层，不得据此生成项目答案。",
                    "- OB-001 中过期促销话术已从运行库排除，只在审计层留档。",
                ]
            ),
        )
        add_document_manifest(
            manifests["audit_raw"], stage, governance_path, "迁移治理记录",
            string_metadata(
                document_id="AUDIT-MIGRATION-GOVERNANCE",
                authority_level="governance_record",
                answer_status="not_for_answering",
                customer_rag_allowed=False,
                original_source_registry_gap=CURRENT_SOURCE_ID not in registered_ids,
                bundle_source_registry_complete=True,
            ),
        )
        write_jsonl(audit_dir / "document_manifest.jsonl", manifests["audit_raw"])
        faq_status = Counter(row["status"] for row in historical_faq)
        rag_types = Counter(row["metadata"]["doc_type"] for row in rag_documents)
        video_risks = Counter(row["risk_level"] for row in video_review)
        snapshot_origins = Counter(row["origin"] for row in snapshot_rows)
        historical_unique_source_ids = {
            match.group(0)
            for path in historical_raw_files
            for match in [re.search(r"SRC-\d{3}", path.name)]
            if match
        }
        output_hash_rows = []
        for path in sorted(stage.rglob("*")):
            if path.is_file() and path.name not in {GENERATOR_MARKER, "bundle_manifest.json"}:
                output_hash_rows.append(
                    {
                        "path": path.relative_to(stage).as_posix(),
                        "sha256": sha256(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
        manifest = {
            "bundle_version": config["bundle_version"],
            "source_version": config["source_version"],
            "weknora": config["weknora"],
            "authority": {
                "current_course_source": "knowledge_base/秀域企业完整知识库_高密度整合版_2026年8月.md",
                "taxonomy_source": TAXONOMY_DOCX,
                "taxonomy_is_content_source": False,
                "current_source_id": CURRENT_SOURCE_ID,
                "current_source_registry_gap_recorded": True,
                "source_registry_extension": "source_registry_extension.json",
                "authority_sha256": source_registry_extension["sha256"],
            },
            "counts": {
                "modules": len(learning_modules["modules"]),
                "courses": len(learning_catalog["courses"]),
                "course_sections": sum(len(course.get("sections", [])) for course in learning_catalog["courses"]),
                "course_paragraphs": sum(
                    len(section.get("content", []))
                    for course in learning_catalog["courses"]
                    for section in course.get("sections", [])
                ),
                "knowledge_cards": len(cards),
                "card_training_questions": sum(len(card.get("question_bank", [])) for card in cards),
                "current_faq": len(current_faq),
                "current_faq_enabled": sum(1 for row in customer_entries[: len(current_faq)] if row["is_enabled"]),
                "current_faq_provisional_disabled": sum(
                    1 for row in current_faq if row.get("risk_level") != "高"
                ),
                "current_faq_high_risk_disabled": sum(1 for row in current_faq if row.get("risk_level") == "高"),
                "historical_faq": len(historical_faq),
                "historical_faq_status": dict(sorted(faq_status.items())),
                "historical_covered_collapsed_entries": len(customer_entries) - len(current_faq),
                "customer_faq_payload_entries": len(customer_entries),
                "safety_boundary_answer_groups": len(boundary_entries),
                "safety_boundary_question_aliases": sum(
                    1 + len(row["similar_questions"]) for row in boundary_entries
                ),
                "safety_boundary_enabled": sum(
                    1 for row in boundary_entries if row["is_enabled"]
                ),
                "safety_boundary_provisional_disabled": sum(
                    1 for row in boundary_entries if not row["is_enabled"]
                ),
                "rag_documents": len(rag_documents),
                "rag_document_types": dict(sorted(rag_types.items())),
                "taxonomy": taxonomy["counts"],
                "video_review_items": len(video_review),
                "video_review_risks": dict(sorted(video_risks.items())),
                "registered_sources_original": source_registry.get("source_count"),
                "registered_sources_effective": int(source_registry.get("source_count", 0)) + 1,
                "source_snapshot_files_total": len(snapshot_rows),
                "source_snapshot_origin_counts": dict(sorted(snapshot_origins.items())),
                "historical_raw_file_count": len(historical_raw_files),
                "historical_unique_source_ids": len(historical_unique_source_ids),
                "staff_documents": len(manifests["staff_courses"]),
                "safety_documents": len(manifests["safety_policy"]),
                "safety_boundary_faq_entries": len(boundary_entries),
                "audit_documents": len(manifests["audit_raw"]),
            },
            "knowledge_bases": config["knowledge_bases"],
            "exclusions": {
                "customer_agent": [
                    "KB-STAFF-COURSES",
                    "KB-AUDIT-RAW",
                    "all pending_review video content",
                    "all material_missing questions",
                    "OB-001 and historical exam answers",
                ],
                "deduplicated_runtime_sources": [
                    "knowledge_cards.content duplicates learning_catalog paragraphs",
                    "rag_documents course_section duplicates learning_catalog sections",
                    "rag_documents common_qa duplicates common_qa_catalog approved answers",
                ],
            },
            "files": output_hash_rows,
        }
        write_json(stage / "bundle_manifest.json", manifest)
        stage.rename(output)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = build_bundle(output)
    print(json.dumps({"output": str(output), "counts": manifest["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
