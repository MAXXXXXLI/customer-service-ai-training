#!/usr/bin/env python3
"""Contract tests for the one-document Runtime safety delta upgrader."""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


MIGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MIGRATION_DIR))

from import_bundle import APIError, EXPECTED_COMMIT, ImportFailure, kb_create_payload  # noqa: E402
from sync_runtime_safety_delta import (  # noqa: E402
    apply_safety_delta,
    load_safety_bundle,
)


KB_ID = "kb-safety"
TENANT_ID = "tenant-runtime"
TENANT_NAME = "Runtime"
EMBEDDING_ID = "model-embedding"
SUMMARY_ID = "model-summary"
DOCUMENT_PATH = "safety_policy/SAFETY-GOVERNANCE-AND-ROUTING.md"


def safety_spec() -> Dict[str, Any]:
    return {
        "key": "safety_policy",
        "name": "KB-SAFETY-POLICY",
        "type": "document",
        "description": "Runtime safety policy",
        "access_policy": "staff_only_until_reviewed",
        "tenant_group": "runtime",
        "chunking_config": {
            "chunk_size": 512,
            "chunk_overlap": 80,
            "separators": ["\n\n", "\n", "。", "！", "？", ";", "；"],
            "strategy": "heading",
            "token_limit": 0,
            "languages": ["zh"],
            "enable_parent_child": False,
            "parent_chunk_size": 4096,
            "child_chunk_size": 384,
        },
    }


def base_metadata() -> Dict[str, str]:
    return {
        "document_id": "SAFETY-GOVERNANCE-AND-ROUTING",
        "authority_level": "enterprise_safety_policy",
        "answer_status": "staff_only_pending_named_review",
        "customer_rag_allowed": "false",
        "effective_from": "2026-08-19",
        "review_owner": "unassigned",
        "source_ids": '["compliance_references.json","customer_service_methodology.json"]',
        "version": "2026-08-integrated-high-density",
    }


def write_bundle(root: Path, version: str, content: str) -> Path:
    bundle = root / version
    safety_dir = bundle / "safety_policy"
    safety_dir.mkdir(parents=True)
    document = safety_dir / "SAFETY-GOVERNANCE-AND-ROUTING.md"
    document.write_text(content, encoding="utf-8")
    file_hash = hashlib.sha256(document.read_bytes()).hexdigest()
    row = {
        "path": DOCUMENT_PATH,
        "title": "顾客回答安全规范与路由方法",
        "sha256": file_hash,
        "size_bytes": document.stat().st_size,
        "metadata": base_metadata(),
    }
    (safety_dir / "document_manifest.jsonl").write_text(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "bundle_version": version,
        "weknora": {"version": "v0.7.2", "commit": EXPECTED_COMMIT},
        "counts": {"safety_documents": 1},
        "knowledge_bases": [safety_spec()],
    }
    (bundle / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle


def write_controls(root: Path, old_bundle: Path) -> Tuple[Path, Path]:
    old = load_safety_bundle(old_bundle, "fixture old")
    receipt = {
        "status": "passed",
        "base_url": "http://127.0.0.1:8080",
        "bundle_version": old.version,
        "bundle_manifest_sha256": old.manifest_sha256,
        "tenant_partition": "runtime",
        "tenant": {"id": TENANT_ID, "name": TENANT_NAME},
        "models": {
            "embedding_model_id": EMBEDDING_ID,
            "summary_model_id": SUMMARY_ID,
        },
        "knowledge_bases": {
            "safety_policy": {
                "id": KB_ID,
                "name": safety_spec()["name"],
                "type": "document",
                "access_policy": "staff_only_until_reviewed",
            }
        },
        "documents": [
            {
                "path": old.relative_path,
                "sha256": old.file_sha256,
                "id": "doc-old",
                "kb_id": KB_ID,
                "file_hash": old.file_md5,
                "metadata": old.remote_metadata,
                "parse_status": "completed",
            }
        ],
    }
    state = {
        "schema_version": 1,
        "bundle_version": old.version,
        "bundle_manifest_sha256": old.manifest_sha256,
        "base_url": "http://127.0.0.1:8080",
        "tenant_partition": "runtime",
        "tenant_id": TENANT_ID,
        "knowledge_bases": {
            "safety_policy": {
                "id": KB_ID,
                "name": safety_spec()["name"],
                "type": "document",
            }
        },
        "documents": {
            old.relative_path: {
                "path": old.relative_path,
                "sha256": old.file_sha256,
                "id": "doc-old",
                "kb_id": KB_ID,
                "file_hash": old.file_md5,
                "metadata": old.remote_metadata,
                "parse_status": "completed",
            }
        },
    }
    receipt_path = root / "import_receipt.runtime.json"
    state_path = root / "import_state.runtime.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt_path, state_path


class FakeWeKnoraClient:
    """Small in-memory model of the v0.7.2 endpoints used by the delta."""

    def __init__(
        self,
        old_bundle: Path,
        *,
        fail_upload: bool = False,
        fail_post_delete_retrieval: bool = False,
    ) -> None:
        self.base_url = "http://127.0.0.1:8080"
        self.fail_upload = fail_upload
        self.fail_post_delete_retrieval = fail_post_delete_retrieval
        self.upload_calls = 0
        self.search_calls = 0
        self.delete_calls: List[str] = []
        self.events: List[str] = []
        self.next_document = 1
        old = load_safety_bundle(old_bundle, "fake old")
        self.documents: Dict[str, Dict[str, Any]] = {
            "doc-old": {
                "id": "doc-old",
                "knowledge_base_id": KB_ID,
                "file_hash": old.file_md5,
                "metadata": old.remote_metadata,
                "parse_status": "completed",
                "error_message": "",
            }
        }
        remote_kb = kb_create_payload(safety_spec(), EMBEDDING_ID, SUMMARY_ID)
        remote_kb.update({"id": KB_ID})
        self.knowledge_bases = [remote_kb]
        self.tags = [{"id": "tag-safety", "name": "safety-policy", "seq_id": 1}]

    @staticmethod
    def _ok(data: Any = None) -> Dict[str, Any]:
        return {"success": True, "data": data}

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Optional[bytes] = None,
        json_body: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        query: Optional[Sequence[Tuple[str, Any]]] = None,
        api: bool = True,
        accepted: Sequence[int] = (200, 201),
    ) -> Any:
        del body, headers, api, accepted
        if method == "GET" and path == "/health":
            return {"status": "ok"}
        if method == "GET" and path == "/system/info":
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "version": "v0.7.2",
                    "commit_id": EXPECTED_COMMIT,
                    "edition": "lite",
                },
            }
        if method == "GET" and path == "/auth/me":
            return self._ok(
                {
                    "user": {"id": "api-key-principal"},
                    "tenant": {"id": TENANT_ID, "name": TENANT_NAME},
                }
            )
        if method == "GET" and path == "/knowledge-bases":
            return self._ok([dict(row) for row in self.knowledge_bases])
        if method == "GET" and path == f"/knowledge-bases/{KB_ID}/tags":
            return self._ok(
                {"data": [dict(row) for row in self.tags], "total": len(self.tags), "page": 1}
            )
        if method == "GET" and path == f"/knowledge-bases/{KB_ID}/knowledge":
            rows = [dict(row) for row in self.documents.values()]
            return {
                "success": True,
                "data": rows,
                "total": len(rows),
                "page": 1,
                "page_size": 1000,
            }
        if method == "GET" and path == "/knowledge/batch":
            ids = [str(value) for key, value in (query or []) if key == "ids"]
            return self._ok([dict(self.documents[item]) for item in ids if item in self.documents])
        if method == "GET" and path.startswith("/knowledge/"):
            document_id = path.rsplit("/", 1)[-1]
            if document_id not in self.documents:
                raise APIError(404, method, self.base_url + "/api/v1" + path, {"message": "not found"})
            return self._ok(dict(self.documents[document_id]))
        if method == "POST" and path == "/knowledge-search":
            self.search_calls += 1
            if self.fail_post_delete_retrieval and self.search_calls >= 2:
                return self._ok([])
            requested = {str(item) for item in (json_body or {}).get("knowledge_base_ids", [])}
            rows = [
                {
                    "id": f"chunk-{document_id}",
                    "knowledge_id": document_id,
                    "knowledge_base_id": row["knowledge_base_id"],
                    "content": "mock safety content",
                    "score": 1.0,
                }
                for document_id, row in self.documents.items()
                if str(row["knowledge_base_id"]) in requested
            ]
            return self._ok(rows)
        if method == "DELETE" and path.startswith("/knowledge/"):
            document_id = path.rsplit("/", 1)[-1]
            self.delete_calls.append(document_id)
            self.events.append(f"delete:{document_id}")
            if document_id not in self.documents:
                raise APIError(404, method, self.base_url + "/api/v1" + path, {"message": "not found"})
            self.documents.pop(document_id)
            return self._ok({"task_id": f"delete-{document_id}"})
        raise AssertionError(f"unexpected fake request: {method} {path}")

    def upload_document(
        self,
        kb_id: str,
        path: Path,
        file_name: str,
        metadata: Mapping[str, str],
        tag_ids: Sequence[str],
        process_config: Mapping[str, Any],
    ) -> Dict[str, Any]:
        del file_name, tag_ids, process_config
        self.upload_calls += 1
        self.events.append(f"upload:{path.name}")
        if self.fail_upload:
            raise ImportFailure("simulated upload failure sk-test-secret")
        document_id = f"doc-upload-{self.next_document}"
        self.next_document += 1
        row = {
            "id": document_id,
            "knowledge_base_id": kb_id,
            "file_hash": hashlib.md5(path.read_bytes()).hexdigest(),  # noqa: S324
            "metadata": dict(metadata),
            "parse_status": "completed",
            "error_message": "",
        }
        self.documents[document_id] = row
        return self._ok(dict(row))


class SafetyDeltaContractTest(unittest.TestCase):
    def fixture(self, raw: str) -> Dict[str, Path]:
        root = Path(raw)
        old_bundle = write_bundle(
            root,
            "2026-08-26-weknora-v5",
            "# 顾客回答安全规范与路由方法\n\n## TOPIC-BODY\n旧路由。\n",
        )
        new_bundle = write_bundle(
            root,
            "2026-08-27-weknora-v6",
            "# 顾客回答安全规范与路由方法\n\n## TOPIC-BODY\n新路由。\n\n"
            "### TOPIC-PRIVATE｜私密健康与盆底服务\n主模块：MOD-10\n",
        )
        runtime_receipt, state = write_controls(root, old_bundle)
        return {
            "root": root,
            "old": old_bundle,
            "new": new_bundle,
            "runtime_receipt": runtime_receipt,
            "state": state,
            "output": root / "import_receipt.runtime.safety-v6-delta.json",
        }

    def apply(self, paths: Mapping[str, Path], client: FakeWeKnoraClient) -> Dict[str, Any]:
        return apply_safety_delta(
            client=client,  # type: ignore[arg-type]
            old_bundle=paths["old"],
            new_bundle=paths["new"],
            runtime_receipt=paths["runtime_receipt"],
            state=paths["state"],
            output_receipt=paths["output"],
            expected_tenant=TENANT_ID,
            wait_timeout=1.0,
            poll_interval=0.0,
        )

    def test_success_uploads_v6_before_async_delete_and_writes_private_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.fixture(raw)
            client = FakeWeKnoraClient(paths["old"])
            receipt = self.apply(paths, client)

            self.assertEqual(receipt["status"], "passed")
            self.assertEqual(client.upload_calls, 1)
            self.assertEqual(client.delete_calls, ["doc-old"])
            self.assertEqual(
                client.events,
                ["upload:SAFETY-GOVERNANCE-AND-ROUTING.md", "delete:doc-old"],
            )
            self.assertEqual(set(client.documents), {"doc-upload-1"})
            new = load_safety_bundle(paths["new"], "assert new")
            self.assertEqual(client.documents["doc-upload-1"]["file_hash"], new.file_md5)
            self.assertEqual(receipt["exact_set"]["document_ids"], ["doc-upload-1"])
            self.assertEqual(len(receipt["retrieval_checks"]), 2)
            self.assertEqual(stat.S_IMODE(paths["output"].stat().st_mode), 0o600)
            text = paths["output"].read_text(encoding="utf-8")
            self.assertNotIn("sk-test-secret", text)
            self.assertEqual(json.loads(text)["status"], "passed")

    def test_upload_failure_never_deletes_old_document(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.fixture(raw)
            client = FakeWeKnoraClient(paths["old"], fail_upload=True)

            with self.assertRaisesRegex(ImportFailure, "simulated upload failure"):
                self.apply(paths, client)

            self.assertEqual(client.delete_calls, [])
            self.assertEqual(set(client.documents), {"doc-old"})
            old = load_safety_bundle(paths["old"], "assert old")
            self.assertEqual(client.documents["doc-old"]["file_hash"], old.file_md5)
            failed = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["rollback"]["status"], "restored_v5")
            self.assertNotIn("sk-test-secret", paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(stat.S_IMODE(paths["output"].stat().st_mode), 0o600)

    def test_post_delete_final_failure_reuploads_v5_before_removing_v6(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self.fixture(raw)
            client = FakeWeKnoraClient(
                paths["old"],
                fail_post_delete_retrieval=True,
            )

            with self.assertRaisesRegex(ImportFailure, "post-delete safety retrieval"):
                self.apply(paths, client)

            self.assertEqual(client.upload_calls, 2)
            self.assertEqual(client.delete_calls, ["doc-old", "doc-upload-1"])
            self.assertEqual(
                client.events,
                [
                    "upload:SAFETY-GOVERNANCE-AND-ROUTING.md",
                    "delete:doc-old",
                    "upload:SAFETY-GOVERNANCE-AND-ROUTING.md",
                    "delete:doc-upload-1",
                ],
            )
            self.assertEqual(set(client.documents), {"doc-upload-2"})
            old = load_safety_bundle(paths["old"], "assert restored old")
            restored = client.documents["doc-upload-2"]
            self.assertEqual(restored["file_hash"], old.file_md5)
            self.assertEqual(restored["metadata"], old.remote_metadata)
            failed = json.loads(paths["output"].read_text(encoding="utf-8"))
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["rollback"]["status"], "restored_v5")
            self.assertEqual(failed["rollback"]["exact_set_ids"], ["doc-upload-2"])
            self.assertEqual(stat.S_IMODE(paths["output"].stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
