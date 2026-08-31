#!/usr/bin/env python3
"""End-to-end contract test for the REST importer using a local fake server."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
from email import policy as email_policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock


MIGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MIGRATION_DIR))

from approve_faq import apply_approval, faq_content, load_approval_plan  # noqa: E402
from import_bundle import (  # noqa: E402
    EXPECTED_COMMIT,
    ImportFailure,
    WeKnoraClient,
    apply_import,
    import_documents,
    import_faq_set,
)
from setup_models import ensure_models, model_specs  # noqa: E402
from setup_access_keys import (  # noqa: E402
    key_specs,
    main as setup_access_keys_main,
    require_approval,
    verify_key_shape,
    verify_live_approval,
)
from verify_bundle import validate_bundle  # noqa: E402


class FakeStore:
    def __init__(self, tenant_id: str = "tenant-runtime", tenant_name: str = "runtime") -> None:
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.kbs: List[Dict[str, Any]] = []
        self.tags: Dict[str, List[Dict[str, Any]]] = {}
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.faq: Dict[str, List[Dict[str, Any]]] = {}
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.models: List[Dict[str, Any]] = []
        self.next_kb = 1
        self.next_tag = 1
        self.next_doc = 1
        self.next_faq = 100000001
        self.next_task = 1
        self.next_model = 1
        self.upload_calls = 0
        self.faq_import_payloads: List[Dict[str, Any]] = []
        self.fail_next_faq_import = False


class FakeHandler(BaseHTTPRequestHandler):
    server_version = "FakeWeKnora/0.7.2"

    @property
    def store(self) -> FakeStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def read_json(self) -> Dict[str, Any]:
        raw = self.read_body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def read_multipart(self) -> Dict[str, bytes]:
        content_type = self.headers.get("Content-Type", "")
        message = BytesParser(policy=email_policy.default).parsebytes(
            b"Content-Type: "
            + content_type.encode("ascii")
            + b"\r\nMIME-Version: 1.0\r\n\r\n"
            + self.read_body()
        )
        return {
            str(part.get_param("name", header="content-disposition")): part.get_payload(
                decode=True
            )
            for part in message.iter_parts()
        }

    def send_value(self, status: int, value: Any) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def ok(self, data: Any = None, status: int = 200) -> None:
        self.send_value(status, {"success": True, "data": data})

    def route(self) -> urllib.parse.ParseResult:
        return urllib.parse.urlparse(self.path)

    def do_GET(self) -> None:  # noqa: N802
        parsed = self.route()
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/health":
            self.ok({"status": "ok"})
            return
        if path == "/api/v1/system/info":
            self.send_value(
                200,
                {
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "version": "0.7.2",
                        "commit_id": EXPECTED_COMMIT,
                        "edition": "standard",
                    },
                },
            )
            return
        if path == "/api/v1/auth/me":
            self.ok(
                {
                    "user": {"id": "api-key-user"},
                    "tenant": {"id": self.store.tenant_id, "name": self.store.tenant_name},
                }
            )
            return
        if path == "/api/v1/knowledge-bases":
            self.ok(self.store.kbs)
            return
        if path == "/api/v1/models":
            self.ok(self.store.models)
            return
        if path == "/api/v1/knowledge/batch":
            ids = query.get("ids", [])
            self.ok([self.store.documents[item] for item in ids if item in self.store.documents])
            return
        if path.startswith("/api/v1/knowledge/"):
            document_id = path.rsplit("/", 1)[-1]
            row = self.store.documents.get(document_id)
            if row is None:
                self.send_value(404, {"success": False, "message": "not found"})
            else:
                self.ok(row)
            return
        if path.startswith("/api/v1/faq/import/progress/"):
            task_id = path.rsplit("/", 1)[-1]
            self.ok(self.store.tasks[task_id])
            return
        parts = path.strip("/").split("/")
        if (
            len(parts) == 5
            and parts[:3] == ["api", "v1", "knowledge-bases"]
            and parts[4] == "knowledge"
        ):
            kb_id = parts[3]
            rows = [
                row
                for row in self.store.documents.values()
                if row.get("knowledge_base_id") == kb_id
            ]
            page = int(query.get("page", ["1"])[0])
            page_size = int(query.get("page_size", ["10"])[0])
            start = (page - 1) * page_size
            self.send_value(
                200,
                {
                    "success": True,
                    "data": rows[start : start + page_size],
                    "total": len(rows),
                    "page": page,
                    "page_size": page_size,
                },
            )
            return
        if len(parts) == 5 and parts[:3] == ["api", "v1", "knowledge-bases"] and parts[4:] == ["tags"]:
            kb_id = parts[3]
            rows = self.store.tags.get(kb_id, [])
            self.ok({"total": len(rows), "page": 1, "page_size": 1000, "data": rows})
            return
        if (
            len(parts) == 6
            and parts[:3] == ["api", "v1", "knowledge-bases"]
            and parts[4:] == ["faq", "entries"]
        ):
            kb_id = parts[3]
            rows = self.store.faq.get(kb_id, [])
            self.ok({"total": len(rows), "page": 1, "page_size": 1000, "data": rows})
            return
        self.send_value(404, {"success": False, "message": path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = self.route()
        path = parsed.path
        if path == "/api/v1/knowledge-bases":
            payload = self.read_json()
            row = dict(payload)
            # Lite v0.7.2 omits the zero-value token_limit when serializing
            # ChunkingConfig, even though zero is the persisted default.
            chunking = dict(row.get("chunking_config") or {})
            if chunking.get("token_limit") == 0:
                chunking.pop("token_limit")
            if chunking.get("enable_parent_child") is False:
                chunking.pop("enable_parent_child")
            row["chunking_config"] = chunking
            row.update({"id": f"kb-{self.store.next_kb}", "knowledge_count": 0, "chunk_count": 0})
            self.store.next_kb += 1
            self.store.kbs.append(row)
            self.store.tags[row["id"]] = []
            self.store.faq[row["id"]] = []
            self.ok(row, status=201)
            return
        if path == "/api/v1/models":
            payload = self.read_json()
            row = dict(payload)
            row["id"] = f"model-{self.store.next_model}"
            self.store.next_model += 1
            # Match the production response contract: credentials are redacted.
            row["parameters"] = {
                key: value
                for key, value in row.get("parameters", {}).items()
                if key != "api_key"
            }
            self.store.models.append(row)
            self.ok(row, status=201)
            return
        if path == "/api/v1/knowledge-search":
            payload = self.read_json()
            requested = payload.get("knowledge_base_ids", [])
            rows: List[Dict[str, Any]] = []
            for kb_id in requested:
                document = next(
                    (
                        row
                        for row in self.store.documents.values()
                        if row.get("knowledge_base_id") == kb_id
                    ),
                    None,
                )
                if document is not None:
                    rows.append(
                        {
                            "id": f"chunk-{document['id']}",
                            "content": "mock document result",
                            "score": 1.0,
                            "knowledge_base_id": kb_id,
                        }
                    )
                    break
                faq = next(
                    (row for row in self.store.faq.get(kb_id, []) if row.get("is_enabled")),
                    None,
                )
                if faq is not None:
                    rows.append(
                        {
                            "id": faq["chunk_id"],
                            "content": faq["answers"][0],
                            "score": 1.0,
                            "knowledge_base_id": kb_id,
                        }
                    )
                    break
            self.ok(rows)
            return
        parts = path.strip("/").split("/")
        if len(parts) == 5 and parts[:3] == ["api", "v1", "knowledge-bases"] and parts[4] == "tags":
            kb_id = parts[3]
            payload = self.read_json()
            row = dict(payload)
            row.update({"id": f"tag-{self.store.next_tag}", "seq_id": self.store.next_tag})
            self.store.next_tag += 1
            self.store.tags[kb_id].append(row)
            self.ok(row)
            return
        if (
            len(parts) == 6
            and parts[:3] == ["api", "v1", "knowledge-bases"]
            and parts[4:] == ["knowledge", "file"]
        ):
            kb_id = parts[3]
            fields = self.read_multipart()
            file_bytes = fields["file"]
            metadata = json.loads(fields["metadata"].decode("utf-8"))
            document_id = f"doc-{self.store.next_doc}"
            self.store.next_doc += 1
            self.store.upload_calls += 1
            row = {
                "id": document_id,
                "knowledge_base_id": kb_id,
                "file_hash": hashlib.md5(file_bytes).hexdigest(),
                "metadata": metadata,
                "parse_status": "completed",
                "error_message": "",
            }
            self.store.documents[document_id] = row
            self.ok(row, status=201)
            return
        if (
            len(parts) == 6
            and parts[:3] == ["api", "v1", "knowledge-bases"]
            and parts[4:] == ["faq", "entries"]
        ):
            kb_id = parts[3]
            payload = self.read_json()
            self.store.faq_import_payloads.append(dict(payload))
            if not payload.get("dry_run") and self.store.fail_next_faq_import:
                self.store.fail_next_faq_import = False
                self.send_value(500, {"success": False, "message": "simulated import failure"})
                return
            task_id = f"task-{self.store.next_task}"
            self.store.next_task += 1
            entries = payload["entries"]
            if not payload.get("dry_run"):
                imported: List[Dict[str, Any]] = []
                for entry in entries:
                    row = dict(entry)
                    if row.get("negative_questions") == []:
                        row["negative_questions"] = None
                    row["id"] = self.store.next_faq
                    row["chunk_id"] = f"faq-chunk-{self.store.next_faq}"
                    row["knowledge_id"] = f"faq-knowledge-{kb_id}"
                    row["knowledge_base_id"] = kb_id
                    # Reproduce the v0.7.2 bulk-import bug addressed by the importer.
                    row["is_recommended"] = False
                    self.store.next_faq += 1
                    imported.append(row)
                self.store.faq[kb_id] = imported
            progress = {
                "task_id": task_id,
                "kb_id": kb_id,
                "status": "completed",
                "progress": 100,
                "total": len(entries),
                "processed": len(entries),
                "success_count": len(entries),
                "failed_count": 0,
                "partial_failed_count": 0,
                "skipped_count": 0,
                "failed_entries": [],
                "dry_run": bool(payload.get("dry_run")),
            }
            self.store.tasks[task_id] = progress
            self.ok({"task_id": task_id})
            return
        self.send_value(404, {"success": False, "message": path})

    def do_PUT(self) -> None:  # noqa: N802
        parsed = self.route()
        path = parsed.path
        parts = path.strip("/").split("/")
        if (
            len(parts) == 7
            and parts[:3] == ["api", "v1", "knowledge-bases"]
            and parts[4:] == ["faq", "entries", "fields"]
        ):
            kb_id = parts[3]
            payload = self.read_json()
            updates = payload.get("by_id", {})
            for row in self.store.faq[kb_id]:
                update = updates.get(str(row["id"]))
                if update:
                    row.update(update)
            self.ok(None)
            return
        self.send_value(404, {"success": False, "message": path})


class AccessKeyStore:
    """Minimal v0.7.2 Owner/scoped-key contract used by setup_access_keys."""

    def __init__(
        self,
        bad_forbidden_contract: bool = False,
        lose_create_response: bool = False,
    ) -> None:
        self.tenant_id = "101"
        self.tenant_name = "runtime"
        self.knowledge_bases = [
            {"id": "kb-staff", "name": "staff"},
            {"id": "kb-customer", "name": "customer"},
            {"id": "kb-policy", "name": "policy"},
            {"id": "kb-boundary", "name": "boundary"},
        ]
        self.api_keys: List[Dict[str, Any]] = []
        self.create_payloads: List[Dict[str, Any]] = []
        self.delete_ids: List[str] = []
        self.list_calls = 0
        self.scope_forbidden_calls = 0
        self.gate_forbidden_calls = 0
        self.next_key_id = 1
        self.bad_forbidden_contract = bad_forbidden_contract
        self.lose_create_response = lose_create_response

    def key_for_token(self, token: str) -> Optional[Dict[str, Any]]:
        return next((row for row in self.api_keys if row.get("api_key") == token), None)


class AccessKeyHandler(BaseHTTPRequestHandler):
    server_version = "FakeWeKnoraAccessKeys/0.7.2"

    @property
    def store(self) -> AccessKeyStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def send_value(self, status: int, value: Any) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def ok(self, data: Any = None, status: int = 200) -> None:
        self.send_value(status, {"success": True, "data": data})

    def is_owner(self) -> bool:
        return self.headers.get("Authorization") == "Bearer owner-test-jwt"

    def scoped_key(self) -> Optional[Dict[str, Any]]:
        return self.store.key_for_token(self.headers.get("X-API-Key", ""))

    def require_owner(self) -> bool:
        if self.is_owner():
            return True
        self.send_value(
            401,
            {"success": False, "error": {"code": 1001, "message": "Unauthorized"}},
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/v1/auth/me":
            if not self.is_owner() and self.scoped_key() is None:
                self.send_value(
                    401,
                    {"success": False, "error": {"code": 1001, "message": "Unauthorized"}},
                )
                return
            self.ok(
                {
                    "user": {"id": "machine-principal"},
                    "tenant": {"id": self.store.tenant_id, "name": self.store.tenant_name},
                }
            )
            return
        if path == f"/api/v1/tenants/{self.store.tenant_id}/api-keys":
            if not self.require_owner():
                return
            self.store.list_calls += 1
            # v0.7.2 list is a direct array and AfterFind exposes decrypted api_key.
            self.ok([dict(row) for row in self.store.api_keys])
            return
        if path == "/api/v1/knowledge-bases":
            key = self.scoped_key()
            if key is None:
                self.send_value(
                    401,
                    {"success": False, "error": {"code": 1001, "message": "Unauthorized"}},
                )
                return
            allowed = {str(item) for item in key["knowledge_base_ids"]}
            self.ok([row for row in self.store.knowledge_bases if row["id"] in allowed])
            return
        self.send_value(404, {"success": False, "message": path})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == f"/api/v1/tenants/{self.store.tenant_id}/api-keys":
            if not self.require_owner():
                return
            payload = self.read_json()
            self.store.create_payloads.append(dict(payload))
            key_id = self.store.next_key_id
            self.store.next_key_id += 1
            token = f"sk-test-{key_id}"
            expires_at = datetime.fromtimestamp(
                int(payload["expires_at_unix"]),
                timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            row = {
                "id": key_id,
                "scope_type": "tenant",
                "name": payload["name"],
                "api_key": token,
                "full_access": bool(payload["full_access"]),
                "knowledge_base_ids": list(payload["knowledge_base_ids"]),
                "capabilities": list(payload["capabilities"]),
                "expires_at": expires_at,
            }
            self.store.api_keys.append(row)
            if self.store.lose_create_response:
                self.send_value(
                    500,
                    {"success": False, "error": {"message": "response lost after commit"}},
                )
                return
            # With SYSTEM_AES_KEY, BeforeSave mutates the just-created struct's
            # api_key to ciphertext; data.token remains the plaintext credential.
            created = dict(row)
            created["api_key"] = f"aes-gcm-ciphertext-for-{key_id}"
            created["token"] = token
            self.ok(created, status=201)
            return
        if path == "/api/v1/knowledge-search":
            key = self.scoped_key()
            if key is None:
                self.send_value(
                    401,
                    {"success": False, "error": {"code": 1001, "message": "Unauthorized"}},
                )
                return
            payload = self.read_json()
            requested = {str(item) for item in payload.get("knowledge_base_ids", [])}
            allowed = {str(item) for item in key["knowledge_base_ids"]}
            if not requested or not requested.issubset(allowed):
                self.store.scope_forbidden_calls += 1
                if self.store.bad_forbidden_contract:
                    self.send_value(403, {"error": "blocked by an unrelated proxy"})
                else:
                    self.send_value(
                        403,
                        {
                            "success": False,
                            "error": {
                                "code": 1002,
                                "message": "API key scope does not allow one or more knowledge bases",
                            },
                        },
                    )
                return
            kb_id = next(iter(requested))
            self.ok(
                [
                    {
                        "id": f"chunk-{kb_id}",
                        "content": "mock retrieval result",
                        "score": 1.0,
                        "knowledge_base_id": kb_id,
                    }
                ]
            )
            return
        if path == "/api/v1/knowledge-bases":
            self.read_json()
            if self.scoped_key() is not None:
                self.store.gate_forbidden_calls += 1
                self.send_value(
                    403,
                    {"error": "Forbidden: API key scope does not allow this operation"},
                )
                return
        self.send_value(404, {"success": False, "message": path})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        prefix = f"/api/v1/tenants/{self.store.tenant_id}/api-keys/"
        if path.startswith(prefix):
            if not self.require_owner():
                return
            key_id = path.removeprefix(prefix)
            self.store.delete_ids.append(key_id)
            self.store.api_keys = [
                row for row in self.store.api_keys if str(row.get("id")) != key_id
            ]
            self.send_value(200, {"success": True})
            return
        self.send_value(404, {"success": False, "message": path})


def write_access_key_receipts(temp: Path, base_url: str) -> tuple[Path, Path]:
    validation = validate_bundle(MIGRATION_DIR / "bundle")
    common = {
        "status": "passed",
        "bundle_version": validation["bundle_version"],
        "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
        "base_url": base_url,
    }
    runtime = {
        **common,
        "tenant_partition": "runtime",
        "tenant": {"id": "101", "name": "runtime"},
        "knowledge_bases": {
            "staff_courses": {"id": "kb-staff"},
            "customer_approved": {"id": "kb-customer"},
            "safety_policy": {"id": "kb-policy"},
            "safety_boundary": {"id": "kb-boundary"},
        },
    }
    audit = {
        **common,
        "tenant_partition": "audit",
        "tenant": {"id": "202", "name": "audit"},
        "knowledge_bases": {"audit_raw": {"id": "kb-audit"}},
    }
    runtime_path = temp / "runtime-receipt.json"
    audit_path = temp / "audit-receipt.json"
    runtime_path.write_text(json.dumps(runtime, ensure_ascii=False), encoding="utf-8")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
    return runtime_path, audit_path


def invoke_access_key_setup(
    base_url: str,
    runtime_receipt: Path,
    audit_receipt: Path,
    output: Path,
    extra_args: Optional[List[str]] = None,
) -> tuple[int, str, str]:
    argv = [
        "setup_access_keys.py",
        "--bundle",
        str(MIGRATION_DIR / "bundle"),
        "--runtime-receipt",
        str(runtime_receipt),
        "--audit-receipt",
        str(audit_receipt),
        "--base-url",
        base_url,
        "--staff-key-name",
        "contract-test-staff-key",
        "--expires-days",
        "30",
        "--output",
        str(output),
        "--apply",
    ]
    argv.extend(extra_args or [])
    stdout = io.StringIO()
    stderr = io.StringIO()
    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.dict(os.environ, {"WEKNORA_OWNER_JWT": "owner-test-jwt"}),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        result = setup_access_keys_main()
    return result, stdout.getvalue(), stderr.getvalue()


class ImportBundleContractTest(unittest.TestCase):
    def test_apply_import_uses_one_read_only_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="weknora-snapshot-contract-") as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source-bundle"
            shutil.copytree(MIGRATION_DIR / "bundle", source)
            expected_validation = validate_bundle(source)
            source_faq = source / "customer_approved" / "faq_entries.json"
            original_entries = json.loads(source_faq.read_text(encoding="utf-8"))
            captured_snapshot: List[Path] = []

            def inspect_snapshot(args: Namespace, validation: Dict[str, Any]) -> Dict[str, Any]:
                snapshot = args.bundle
                captured_snapshot.append(snapshot)
                mutated = json.loads(source_faq.read_text(encoding="utf-8"))
                mutated[0]["answers"] = ["MUTATED-AFTER-SNAPSHOT-VALIDATION"]
                source_faq.write_text(json.dumps(mutated, ensure_ascii=False), encoding="utf-8")
                snapshot_entries = json.loads(
                    (snapshot / "customer_approved" / "faq_entries.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(snapshot_entries, original_entries)
                self.assertEqual(snapshot.stat().st_mode & 0o222, 0)
                self.assertEqual(
                    (snapshot / "customer_approved" / "faq_entries.json").stat().st_mode
                    & 0o222,
                    0,
                )
                return {"bundle_manifest_sha256": validation["bundle_manifest_sha256"]}

            args = Namespace(
                bundle=source,
                state=temp / "state.json",
                receipt=temp / "receipt.json",
                peer_receipt=temp / "peer-receipt.json",
            )
            with mock.patch(
                "import_bundle._apply_import_from_snapshot",
                side_effect=inspect_snapshot,
            ):
                result = apply_import(args, expected_validation)
            self.assertEqual(
                result["bundle_manifest_sha256"],
                expected_validation["bundle_manifest_sha256"],
            )
            self.assertEqual(len(captured_snapshot), 1)
            self.assertFalse(captured_snapshot[0].exists())

    def test_generated_approval_templates_are_complete_and_fail_closed(self) -> None:
        bundle = MIGRATION_DIR / "bundle"
        cases = (
            ("customer", "customer_approved", 49),
            ("safety-boundary", "safety_boundary", 9),
        )
        for scope, directory, expected_count in cases:
            entries, approvals, desired = load_approval_plan(
                bundle,
                scope,
                bundle / directory / "approval_template.jsonl",
            )
            self.assertEqual(len(entries), expected_count)
            self.assertEqual(len(approvals), expected_count)
            self.assertEqual(len(desired), expected_count)
            self.assertFalse(any(desired.values()))

    def test_faq_dry_run_does_not_claim_managed_ownership(self) -> None:
        store = FakeStore()
        store.faq["kb-faq"] = []
        store.fail_next_faq_import = True
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix="weknora-faq-attempt-test-") as temp_dir:
                state_path = Path(temp_dir) / "state.json"
                validation = validate_bundle(MIGRATION_DIR / "bundle")
                state: Dict[str, Any] = {
                    "bundle_version": validation["bundle_version"],
                    "faq_imports": {},
                }
                client = WeKnoraClient(
                    f"http://127.0.0.1:{server.server_port}",
                    "test-api-key",
                )
                with self.assertRaises(ImportFailure):
                    import_faq_set(
                        client,
                        MIGRATION_DIR / "bundle",
                        "customer_approved",
                        "kb-faq",
                        state,
                        state_path,
                        timeout=10.0,
                        poll_interval=0.01,
                        allow_replace_existing=False,
                    )
                self.assertNotIn("customer_approved", state["faq_imports"])
                self.assertIn("dry_run", state["faq_attempts"]["customer_approved"])
                self.assertNotIn("kb_id", state["faq_attempts"]["customer_approved"])

                store.faq["kb-faq"] = [
                    {
                        "id": 999000001,
                        "chunk_id": "external-chunk",
                        "knowledge_base_id": "kb-faq",
                        "standard_question": "third-party FAQ",
                    }
                ]
                requests_before = len(store.faq_import_payloads)
                with self.assertRaisesRegex(ImportFailure, "already has 1 entries"):
                    import_faq_set(
                        client,
                        MIGRATION_DIR / "bundle",
                        "customer_approved",
                        "kb-faq",
                        state,
                        state_path,
                        timeout=10.0,
                        poll_interval=0.01,
                        allow_replace_existing=False,
                    )
                self.assertEqual(len(store.faq_import_payloads), requests_before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_access_key_specs_are_nonempty_and_customer_cannot_read_staff_policy(self) -> None:
        receipt = {
            "knowledge_bases": {
                "staff_courses": {"id": "staff"},
                "customer_approved": {"id": "customer"},
                "safety_policy": {"id": "policy"},
                "safety_boundary": {"id": "boundary"},
            }
        }
        specs = key_specs(
            receipt,
            "staff-key",
            "customer-key",
            True,
            True,
            requested_expires_at=2_000_000_000,
            customer_positive_query="已审核顾客问题",
            customer_approval_expires_at=1_999_999_000,
            customer_enabled_chunk_ids=["customer-chunk"],
            boundary_positive_query="已审核边界问题",
            boundary_approval_expires_at=1_999_998_000,
            boundary_enabled_chunk_ids=["boundary-chunk"],
        )
        by_key = {row["key"]: row for row in specs}
        self.assertEqual(by_key["staff"]["knowledge_base_ids"], ["staff", "policy", "boundary"])
        self.assertEqual(by_key["customer"]["knowledge_base_ids"], ["customer", "boundary"])
        self.assertNotIn("staff", by_key["customer"]["knowledge_base_ids"])
        self.assertNotIn("policy", by_key["customer"]["knowledge_base_ids"])
        for spec in specs:
            verify_key_shape(
                {
                    "scope_type": "tenant",
                    "full_access": False,
                    "capabilities": ["retrieve"],
                    "knowledge_base_ids": spec["knowledge_base_ids"],
                    "expires_at": datetime.fromtimestamp(
                        spec["expires_at_unix"],
                        timezone.utc,
                    ).isoformat(),
                },
                spec,
            )

    def test_access_key_owner_create_list_reuse_and_expiry_contract(self) -> None:
        store = AccessKeyStore()
        server = ThreadingHTTPServer(("127.0.0.1", 0), AccessKeyHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory(prefix="weknora-access-key-test-") as temp_dir:
                temp = Path(temp_dir)
                runtime_receipt, audit_receipt = write_access_key_receipts(temp, base_url)
                secret_file = temp / "runtime-access-keys.json"

                first_code, first_stdout, first_stderr = invoke_access_key_setup(
                    base_url,
                    runtime_receipt,
                    audit_receipt,
                    secret_file,
                )
                self.assertEqual(first_code, 0, first_stderr)
                first_result = json.loads(first_stdout)
                self.assertEqual(first_result["status"], "passed")
                self.assertFalse(first_result["keys"][0]["reused"])
                self.assertEqual(len(store.create_payloads), 1)
                create_payload = store.create_payloads[0]
                self.assertIs(create_payload["full_access"], False)
                self.assertEqual(create_payload["capabilities"], ["retrieve"])
                self.assertEqual(
                    set(create_payload["knowledge_base_ids"]),
                    {"kb-staff", "kb-policy"},
                )
                self.assertEqual(len(store.api_keys), 1)
                self.assertEqual(
                    first_result["keys"][0]["expires_at_unix"],
                    create_payload["expires_at_unix"],
                )
                secret = json.loads(secret_file.read_text(encoding="utf-8"))
                self.assertEqual(secret["keys"]["staff"]["token"], "sk-test-1")
                self.assertNotIn("sk-test-1", first_stdout)
                self.assertEqual(store.scope_forbidden_calls, 2)
                self.assertEqual(store.gate_forbidden_calls, 1)

                # Prove reuse can recover solely from v0.7.2 list.api_key after
                # a lost local secret file; no second POST is allowed.
                secret_file.unlink()
                second_code, second_stdout, second_stderr = invoke_access_key_setup(
                    base_url,
                    runtime_receipt,
                    audit_receipt,
                    secret_file,
                )
                self.assertEqual(second_code, 0, second_stderr)
                second_result = json.loads(second_stdout)
                self.assertTrue(second_result["keys"][0]["reused"])
                self.assertEqual(len(store.create_payloads), 1)
                recovered = json.loads(secret_file.read_text(encoding="utf-8"))
                self.assertEqual(recovered["keys"]["staff"]["token"], "sk-test-1")

                # List includes unrevoked-but-overlong keys in v0.7.2; setup
                # must reject one whose RFC3339 expiry exceeds today's policy.
                store.api_keys[0]["expires_at"] = (
                    datetime.now(timezone.utc) + timedelta(days=400)
                ).isoformat()
                third_code, _, third_stderr = invoke_access_key_setup(
                    base_url,
                    runtime_receipt,
                    audit_receipt,
                    secret_file,
                )
                self.assertEqual(third_code, 1)
                self.assertIn("expiry exceeds", third_stderr)
                self.assertEqual(len(store.create_payloads), 1)
                self.assertEqual(store.delete_ids, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_access_key_rejects_unrelated_403_and_rolls_back_new_key(self) -> None:
        store = AccessKeyStore(bad_forbidden_contract=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), AccessKeyHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory(prefix="weknora-access-rollback-test-") as temp_dir:
                temp = Path(temp_dir)
                runtime_receipt, audit_receipt = write_access_key_receipts(temp, base_url)
                secret_file = temp / "runtime-access-keys.json"
                code, stdout, stderr = invoke_access_key_setup(
                    base_url,
                    runtime_receipt,
                    audit_receipt,
                    secret_file,
                )
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertIn("expected the scoped-key 403 contract", stderr)
                self.assertEqual(len(store.create_payloads), 1)
                self.assertEqual(store.delete_ids, ["1"])
                self.assertEqual(store.api_keys, [])
                rolled_back = json.loads(secret_file.read_text(encoding="utf-8"))
                self.assertEqual(rolled_back["keys"], {})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_access_key_recovers_and_revokes_after_create_response_loss(self) -> None:
        store = AccessKeyStore(lose_create_response=True)
        server = ThreadingHTTPServer(("127.0.0.1", 0), AccessKeyHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory(prefix="weknora-access-lost-response-test-") as temp_dir:
                temp = Path(temp_dir)
                runtime_receipt, audit_receipt = write_access_key_receipts(temp, base_url)
                code, stdout, stderr = invoke_access_key_setup(
                    base_url,
                    runtime_receipt,
                    audit_receipt,
                    temp / "runtime-access-keys.json",
                )
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertIn("HTTP 500", stderr)
                self.assertEqual(len(store.create_payloads), 1)
                self.assertEqual(store.delete_ids, ["1"])
                self.assertEqual(store.api_keys, [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_access_key_post_snapshot_drift_revokes_only_affected_key(self) -> None:
        store = AccessKeyStore()
        server = ThreadingHTTPServer(("127.0.0.1", 0), AccessKeyHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with tempfile.TemporaryDirectory(prefix="weknora-access-snapshot-test-") as temp_dir:
                temp = Path(temp_dir)
                runtime_receipt, audit_receipt = write_access_key_receipts(temp, base_url)
                secret_file = temp / "runtime-access-keys.json"
                approval = {
                    "knowledge_base_id": "kb-customer",
                    "enabled_count": 1,
                    "faq_snapshot": {
                        "enabled_entries": [{"chunk_id": "chunk-kb-customer"}],
                    },
                    "_approved_expiry_unix": int(
                        (datetime.now(timezone.utc) + timedelta(days=20)).timestamp()
                    ),
                    "_positive_query": "approved customer query",
                }
                with (
                    mock.patch("setup_access_keys.require_approval", return_value=approval),
                    mock.patch(
                        "setup_access_keys.verify_live_approval",
                        side_effect=[{"sha256": "approved"}, ImportFailure("snapshot drift")],
                    ),
                ):
                    code, stdout, stderr = invoke_access_key_setup(
                        base_url,
                        runtime_receipt,
                        audit_receipt,
                        secret_file,
                        [
                            "--create-customer",
                            "--customer-approval-receipt",
                            str(temp / "approval-receipt.json"),
                        ],
                    )
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertIn("every affected scoped key was revoked", stderr)
                self.assertEqual(len(store.create_payloads), 2)
                self.assertEqual(store.delete_ids, ["2"])
                self.assertEqual([row["name"] for row in store.api_keys], ["contract-test-staff-key"])
                secrets = json.loads(secret_file.read_text(encoding="utf-8"))
                self.assertEqual(set(secrets["keys"]), {"staff"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_model_setup_is_idempotent_and_does_not_return_secret(self) -> None:
        store = FakeStore()
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            from import_bundle import WeKnoraClient

            client = WeKnoraClient(f"http://127.0.0.1:{server.server_port}", "test-key")
            first = ensure_models(client, model_specs("Qwen/Qwen3.6-35B-A3B", "secret-upstream-key"))
            second = ensure_models(client, model_specs("Qwen/Qwen3.6-35B-A3B", "secret-upstream-key"))
            self.assertEqual(len(store.models), 3)
            self.assertEqual(
                {key: row["id"] for key, row in first.items()},
                {key: row["id"] for key, row in second.items()},
            )
            self.assertNotIn("secret-upstream-key", json.dumps(second))
            self.assertTrue(all(row["reused"] for row in second.values()))
            chat = next(row for row in store.models if row["type"] == "KnowledgeQA")
            self.assertEqual(
                chat["parameters"]["extra_config"],
                {"thinking_control": "enable_thinking"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_full_import_and_idempotent_rerun(self) -> None:
        store = FakeStore()
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            bundle = MIGRATION_DIR / "bundle"
            validation = validate_bundle(bundle)
            with tempfile.TemporaryDirectory(prefix="weknora-import-test-") as temp_dir:
                temp = Path(temp_dir)
                args = Namespace(
                    bundle=bundle,
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    state=temp / "state.json",
                    receipt=temp / "receipt.json",
                    api_key="test-api-key",
                    embedding_model_id="embedding-model-id",
                    summary_model_id="summary-model-id",
                    scope="runtime",
                    expected_tenant_id="tenant-runtime",
                    peer_receipt=temp / "audit-receipt.json",
                    adopt_existing_kbs=False,
                    replace_existing_faq=False,
                    allow_version_mismatch=False,
                    wait_timeout=10.0,
                    poll_interval=0.01,
                    http_timeout=10.0,
                )
                receipt = apply_import(args, validation)
                self.assertEqual(receipt["status"], "passed")
                self.assertEqual(receipt["tenant"]["id"], "tenant-runtime")
                self.assertEqual(len(store.kbs), 4)
                self.assertEqual(store.upload_calls, 45 + 1)
                self.assertEqual(sum(len(rows) for rows in store.faq.values()), 49 + 9)
                self.assertFalse(any(row["is_recommended"] for row in store.faq["kb-4"]))
                self.assertEqual(
                    sum(bool(row["is_recommended"]) for row in store.faq["kb-2"]),
                    0,
                )
                self.assertEqual(receipt["agent_binding_policy"]["never_bind"], ["audit_raw"])
                smoke = {row["name"]: row for row in receipt["retrieval_smoke_tests"]}
                self.assertEqual(smoke["customer-provisional-disabled"]["result_count"], 0)
                self.assertGreater(smoke["staff-course"]["result_count"], 0)
                self.assertGreater(smoke["safety-policy"]["result_count"], 0)
                self.assertEqual(
                    smoke["safety-boundary-provisional-disabled"]["result_count"],
                    0,
                )
                first_upload_count = store.upload_calls

                # A rerun uses the state file, reuses all documents, and safely
                # replaces only the two migration-managed FAQ sets.
                second = apply_import(args, validation)
                self.assertEqual(second["status"], "passed")
                self.assertEqual(store.upload_calls, first_upload_count)
                self.assertEqual(len(store.kbs), 4)
                self.assertEqual(sum(len(rows) for rows in store.faq.values()), 49 + 9)

                manifest = json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
                runtime_specs = [
                    row
                    for row in manifest["knowledge_bases"]
                    if row.get("tenant_group") == "runtime"
                ]
                document_client = WeKnoraClient(args.base_url, "test-api-key")

                def rerun_documents() -> None:
                    import_documents(
                        document_client,
                        bundle,
                        runtime_specs,
                        second["knowledge_bases"],
                        json.loads(args.state.read_text(encoding="utf-8")),
                        args.state,
                        timeout=10.0,
                        poll_interval=0.01,
                    )

                staff_kb_id = str(second["knowledge_bases"]["staff_courses"]["id"])
                victim = next(
                    row
                    for row in store.documents.values()
                    if row["knowledge_base_id"] == staff_kb_id
                )
                original_kb_id = victim["knowledge_base_id"]
                victim["knowledge_base_id"] = str(second["knowledge_bases"]["safety_policy"]["id"])
                with self.assertRaisesRegex(ImportFailure, "knowledge_base_id drifted"):
                    rerun_documents()
                victim["knowledge_base_id"] = original_kb_id

                original_file_hash = victim["file_hash"]
                victim["file_hash"] = "0" * 32
                with self.assertRaisesRegex(ImportFailure, "file_hash differs"):
                    rerun_documents()
                victim["file_hash"] = original_file_hash

                original_metadata = dict(victim["metadata"])
                victim["metadata"]["bundle_sha256"] = "0" * 64
                with self.assertRaisesRegex(ImportFailure, "metadata drifted"):
                    rerun_documents()
                victim["metadata"] = original_metadata

                store.documents["evil-extra"] = {
                    "id": "evil-extra",
                    "knowledge_base_id": staff_kb_id,
                    "file_hash": "0" * 32,
                    "metadata": {"bundle_path": "evil-extra.md"},
                    "parse_status": "completed",
                    "error_message": "",
                }
                with self.assertRaisesRegex(ImportFailure, "exact-set mismatch"):
                    rerun_documents()
                del store.documents["evil-extra"]

                approval_rows = [
                    json.loads(line)
                    for line in (
                        bundle / "customer_approved" / "approval_template.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                today = date.today()
                approval_rows[0].update(
                    {
                        "decision": "approved",
                        "review_owner": "business-reviewer",
                        "last_verified_at": today.isoformat(),
                        "effective_from": today.isoformat(),
                        "expires_on": (today + timedelta(days=365)).isoformat(),
                    }
                )
                approval_path = temp / "customer-approval.jsonl"
                approval_path.write_text(
                    "".join(
                        json.dumps(row, ensure_ascii=False) + "\n"
                        for row in approval_rows
                    ),
                    encoding="utf-8",
                )
                verified_entries, approvals, desired = load_approval_plan(
                    bundle,
                    "customer",
                    approval_path,
                )
                approval_args = Namespace(
                    scope="customer",
                    bundle=bundle,
                    import_receipt=args.receipt,
                    base_url=args.base_url,
                    api_key="test-api-key",
                    http_timeout=10.0,
                    allow_version_mismatch=False,
                    output=temp / "approval-receipt.json",
                )
                approval_receipt = apply_approval(
                    approval_args,
                    validation,
                    approvals,
                    desired,
                    verified_entries,
                )
                self.assertEqual(approval_receipt["enabled_count"], 1)
                self.assertEqual(
                    sum(bool(row["is_enabled"]) for row in store.faq["kb-2"]),
                    1,
                )
                self.assertTrue(approval_receipt["approvals"][0]["standard_question"])
                self.assertEqual(approval_receipt["faq_snapshot"]["enabled_count"], 1)
                checked_approval = require_approval(
                    approval_args.output,
                    "customer",
                    second,
                    bundle,
                )
                live_snapshot = verify_live_approval(
                    WeKnoraClient(args.base_url, "test-api-key"),
                    checked_approval,
                    "test customer approval",
                )
                self.assertEqual(
                    live_snapshot["sha256"],
                    approval_receipt["faq_snapshot"]["sha256"],
                )
                store.faq["kb-2"][0]["answers"] = ["tampered after approval"]
                with self.assertRaises(ImportFailure):
                    verify_live_approval(
                        WeKnoraClient(args.base_url, "test-api-key"),
                        checked_approval,
                        "test customer approval after drift",
                    )
                store.faq["kb-2"][0]["answers"] = list(
                    json.loads(
                        (bundle / "customer_approved" / "faq_entries.json").read_text(
                            encoding="utf-8"
                        )
                    )[0]["answers"]
                )

                expired_receipt = dict(approval_receipt)
                expired_receipt["approvals"] = [dict(row) for row in approval_receipt["approvals"]]
                expired_receipt["approvals"][0]["expires_on"] = (
                    today - timedelta(days=1)
                ).isoformat()
                expired_path = temp / "expired-approval-receipt.json"
                expired_path.write_text(
                    json.dumps(expired_receipt, ensure_ascii=False),
                    encoding="utf-8",
                )
                with self.assertRaises(ImportFailure):
                    require_approval(expired_path, "customer", second, bundle)

                # A receipt write failure occurs after remote flags may already
                # be enabled. The publisher must disable the entire FAQ KB.
                expected_faq = json.loads(
                    (bundle / "customer_approved" / "faq_entries.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    faq_content(store.faq["kb-2"][0]),
                    faq_content(expected_faq[0]),
                )
                def fail_only_passed_receipt(path: Path, value: Dict[str, Any]) -> None:
                    if value.get("status") == "passed":
                        raise OSError("simulated disk full")
                    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

                with mock.patch(
                    "approve_faq.write_json_atomic",
                    side_effect=fail_only_passed_receipt,
                ):
                    with self.assertRaises(ImportFailure) as failure:
                        apply_approval(
                            approval_args,
                            validation,
                            approvals,
                            desired,
                            verified_entries,
                        )
                self.assertIn("every FAQ", str(failure.exception))
                self.assertFalse(any(row["is_enabled"] for row in store.faq["kb-2"]))
                self.assertFalse(any(row["is_recommended"] for row in store.faq["kb-2"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_audit_import_requires_a_different_tenant(self) -> None:
        store = FakeStore("tenant-audit", "audit")
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
        server.store = store  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            bundle = MIGRATION_DIR / "bundle"
            validation = validate_bundle(bundle)
            with tempfile.TemporaryDirectory(prefix="weknora-audit-import-test-") as temp_dir:
                temp = Path(temp_dir)
                runtime_receipt = temp / "runtime-receipt.json"
                runtime_receipt.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "tenant_partition": "runtime",
                            "bundle_version": validation["bundle_version"],
                            "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
                            "base_url": f"http://127.0.0.1:{server.server_port}",
                            "tenant": {"id": "tenant-runtime", "name": "runtime"},
                        }
                    ),
                    encoding="utf-8",
                )
                args = Namespace(
                    bundle=bundle,
                    base_url=f"http://127.0.0.1:{server.server_port}",
                    state=temp / "audit-state.json",
                    receipt=temp / "audit-receipt.json",
                    peer_receipt=runtime_receipt,
                    api_key="test-audit-api-key",
                    embedding_model_id="embedding-model-id",
                    summary_model_id="summary-model-id",
                    scope="audit",
                    expected_tenant_id="tenant-audit",
                    adopt_existing_kbs=False,
                    replace_existing_faq=False,
                    allow_version_mismatch=False,
                    wait_timeout=10.0,
                    poll_interval=0.01,
                    http_timeout=10.0,
                )
                receipt = apply_import(args, validation)
                self.assertEqual(receipt["status"], "passed")
                self.assertEqual(receipt["tenant_partition"], "audit")
                self.assertEqual(receipt["tenant"]["id"], "tenant-audit")
                self.assertEqual(
                    receipt["bundle_manifest_sha256"],
                    validation["bundle_manifest_sha256"],
                )
                self.assertEqual(len(store.kbs), 1)
                self.assertEqual(store.upload_calls, validation["counts"]["audit_documents"])
                self.assertFalse(any(store.faq.values()))

                same_tenant_receipt = temp / "same-tenant-runtime-receipt.json"
                same_tenant_receipt.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "tenant_partition": "runtime",
                            "bundle_version": validation["bundle_version"],
                            "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
                            "base_url": f"http://127.0.0.1:{server.server_port}",
                            "tenant": {"id": "tenant-audit", "name": "wrong"},
                        }
                    ),
                    encoding="utf-8",
                )
                args.peer_receipt = same_tenant_receipt
                with self.assertRaises(ImportFailure):
                    apply_import(args, validation)

                wrong_digest_receipt = temp / "wrong-digest-runtime-receipt.json"
                wrong_digest_receipt.write_text(
                    json.dumps(
                        {
                            "status": "passed",
                            "tenant_partition": "runtime",
                            "bundle_version": validation["bundle_version"],
                            "bundle_manifest_sha256": "0" * 64,
                            "base_url": f"http://127.0.0.1:{server.server_port}",
                            "tenant": {"id": "tenant-runtime", "name": "runtime"},
                        }
                    ),
                    encoding="utf-8",
                )
                args.peer_receipt = wrong_digest_receipt
                with self.assertRaisesRegex(ImportFailure, "different bundle content"):
                    apply_import(args, validation)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
