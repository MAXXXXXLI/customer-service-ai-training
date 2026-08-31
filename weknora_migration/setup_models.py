#!/usr/bin/env python3
"""Create or reuse the three remote SiliconFlow models required by the migration."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

from import_bundle import (
    APIError,
    ImportFailure,
    WeKnoraClient,
    ensure_server_version,
    envelope_data,
    flatten_page_data,
    write_json_atomic,
)


MIGRATION_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = MIGRATION_DIR / "model_ids.json"
DEFAULT_CHAT_MODEL = "Qwen/Qwen3.5-35B-A3B"


def model_specs(chat_model: str, upstream_key: str) -> List[Dict[str, Any]]:
    common = {
        "source": "remote",
        "parameters": {
            "provider": "siliconflow",
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key": upstream_key,
        },
    }
    return [
        {
            "key": "embedding",
            "name": "BAAI/bge-m3",
            "display_name": "BGE-M3 (SiliconFlow, 1024d)",
            "type": "Embedding",
            "description": "秀域与春语中文知识检索嵌入模型",
            **common,
            "parameters": {
                **common["parameters"],
                "embedding_parameters": {"dimension": 1024},
            },
        },
        {
            "key": "rerank",
            "name": "BAAI/bge-reranker-v2-m3",
            "display_name": "BGE Reranker v2 M3 (SiliconFlow)",
            "type": "Rerank",
            "description": "中文知识库重排模型",
            **common,
        },
        {
            "key": "chat",
            "name": chat_model,
            "display_name": f"培训问答模型｜{chat_model}",
            "type": "KnowledgeQA",
            "description": "知识摘要、检索改写和员工问答模型",
            **common,
            "parameters": {
                **common["parameters"],
                # SiliconFlow Qwen reasoning models otherwise consume the
                # whole non-stream completion budget as reasoning and may
                # return an empty content field.  WeKnora maps this strict
                # override to enable_thinking=false on every request.
                "extra_config": {"thinking_control": "enable_thinking"},
            },
        },
    ]


def public_payload(spec: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in spec.items() if key != "key"}


def ensure_models(
    client: WeKnoraClient,
    specs: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    listed = flatten_page_data(
        envelope_data(client.request("GET", "/models"), "list models"),
        "list models",
    )
    results: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        matches = [
            row
            for row in listed
            if row.get("name") == spec["name"] and row.get("type") == spec["type"]
        ]
        if len(matches) > 1:
            raise ImportFailure(
                f"ambiguous model {spec['type']}/{spec['name']}: {len(matches)} matches"
            )
        if matches:
            model = matches[0]
            if model.get("source") != "remote":
                raise ImportFailure(
                    f"existing model {spec['type']}/{spec['name']} has source={model.get('source')!r}; "
                    "expected 'remote'"
                )
            reused = True
        else:
            model = envelope_data(
                client.request("POST", "/models", json_body=public_payload(spec), accepted=(201,)),
                f"create model {spec['type']}/{spec['name']}",
            )
            if not isinstance(model, dict) or not model.get("id"):
                raise ImportFailure(f"model creation returned no ID: {spec['type']}/{spec['name']}")
            listed.append(model)
            reused = False
        results[spec["key"]] = {
            "id": model["id"],
            "name": spec["name"],
            "type": spec["type"],
            "source": model.get("source"),
            "reused": reused,
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("WEKNORA_URL", "http://127.0.0.1:18081"))
    parser.add_argument("--api-key", default="", help="prefer WEKNORA_API_KEY to avoid shell history")
    parser.add_argument(
        "--chat-model",
        default=os.environ.get("SILICONFLOW_CHAT_MODEL", DEFAULT_CHAT_MODEL),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-version-mismatch", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("WEKNORA_API_KEY", "")
    upstream_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key or not upstream_key:
        print(
            "model setup failed: WEKNORA_API_KEY and SILICONFLOW_API_KEY are required",
            file=sys.stderr,
        )
        return 1
    try:
        client = WeKnoraClient(args.base_url, api_key)
        server = ensure_server_version(client, args.allow_version_mismatch)
        models = ensure_models(client, model_specs(args.chat_model, upstream_key))
        result = {
            "status": "ready",
            "server": server,
            "models": models,
            "environment": {
                "WEKNORA_EMBEDDING_MODEL_ID": models["embedding"]["id"],
                "WEKNORA_SUMMARY_MODEL_ID": models["chat"]["id"],
                "WEKNORA_RERANK_MODEL_ID": models["rerank"]["id"],
            },
            "note": "No SiliconFlow secret is stored in this file.",
        }
        write_json_atomic(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (APIError, ImportFailure, KeyError, ValueError) as exc:
        print(f"model setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
