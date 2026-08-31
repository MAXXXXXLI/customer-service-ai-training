#!/usr/bin/env python3
"""Contract tests for the WeKnora v0.7.2 Lite provisioning lifecycle."""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MIGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MIGRATION_DIR))

from import_bundle import EXPECTED_COMMIT, ImportFailure  # noqa: E402
from lite_provision import (  # noqa: E402
    OUT_OF_SCOPE_PROBE_ID,
    RUNTIME_KB_KEYS,
    auto_setup,
    main as lite_provision_main,
)


class LiteStore:
    def __init__(self) -> None:
        self.tenant_id = "1"
        self.tenant_name = "WeKnora Lite"
        self.owner_token = "owner-jwt-must-never-be-printed"
        self.knowledge_bases = [
            {"id": "kb-staff", "name": "staff"},
            {"id": "kb-customer", "name": "customer"},
            {"id": "kb-policy", "name": "policy"},
            {"id": "kb-boundary", "name": "boundary"},
        ]
        self.api_keys: List[Dict[str, Any]] = []
        self.next_key_id = 10
        self.auto_setup_calls = 0
        self.create_payloads: List[Dict[str, Any]] = []
        self.delete_ids: List[str] = []
        self.allowed_search_calls = 0
        self.forbidden_search_calls = 0
        self.forbidden_write_calls = 0
        self.allow_scoped_write = False

    def key_for_token(self, token: str) -> Optional[Dict[str, Any]]:
        return next(
            (row for row in self.api_keys if row.get("api_key") == token),
            None,
        )

    def add_key(
        self,
        name: str,
        *,
        full_access: bool,
        kb_ids: Optional[List[str]] = None,
        capabilities: Optional[List[str]] = None,
        token: Optional[str] = None,
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        key_id = self.next_key_id
        self.next_key_id += 1
        token = token or f"sk-fake-secret-{key_id}"
        row = {
            "id": key_id,
            "scope_type": "tenant",
            "name": name,
            "api_key": token,
            "full_access": full_access,
            "knowledge_base_ids": list(kb_ids or []),
            "capabilities": list(capabilities or []),
            "expires_at": datetime.fromtimestamp(
                int(time.time()) + expires_in,
                timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
        }
        self.api_keys.append(row)
        return row


class LiteHandler(BaseHTTPRequestHandler):
    server_version = "FakeWeKnoraLite/0.7.2"

    @property
    def store(self) -> LiteStore:
        return self.server.store  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def path_only(self) -> str:
        return urllib.parse.urlsplit(self.path).path

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
        return self.headers.get("Authorization") == f"Bearer {self.store.owner_token}"

    def current_key(self) -> Optional[Dict[str, Any]]:
        return self.store.key_for_token(self.headers.get("X-API-Key", ""))

    def authenticated(self) -> bool:
        return self.is_owner() or self.current_key() is not None

    def require_owner(self) -> bool:
        if self.is_owner():
            return True
        self.send_value(401, {"success": False, "error": {"message": "unauthorized"}})
        return False

    def do_GET(self) -> None:  # noqa: N802
        path = self.path_only()
        if path == "/api/v1/auth/me":
            if not self.authenticated():
                self.send_value(401, {"success": False, "error": {"message": "unauthorized"}})
                return
            self.ok(
                {
                    "user": {"id": "lite-user"},
                    "tenant": {"id": self.store.tenant_id, "name": self.store.tenant_name},
                }
            )
            return
        if path == "/api/v1/system/info":
            if not self.require_owner():
                return
            # v0.7.2 SystemHandler uses its older code/msg/data envelope.
            self.send_value(
                200,
                {
                    "code": 0,
                    "msg": "success",
                    "data": {
                    "version": "0.7.2",
                    "commit_id": EXPECTED_COMMIT,
                    "edition": "lite",
                    },
                },
            )
            return
        if path == f"/api/v1/tenants/{self.store.tenant_id}/api-keys":
            if not self.require_owner():
                return
            self.ok([dict(row) for row in self.store.api_keys])
            return
        if path == "/api/v1/knowledge-bases":
            key = self.current_key()
            if key is None:
                self.send_value(401, {"success": False, "error": {"message": "unauthorized"}})
                return
            if key["full_access"]:
                self.ok(self.store.knowledge_bases)
            else:
                allowed = {str(item) for item in key["knowledge_base_ids"]}
                self.ok([row for row in self.store.knowledge_bases if row["id"] in allowed])
            return
        self.send_value(404, {"success": False, "message": path})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path_only()
        if path == "/api/v1/auth/auto-setup":
            self.read_json()
            # The production route is unauthenticated and returns a direct
            # AuthLoginResponse rather than the normal success envelope.
            if self.headers.get("Authorization") or self.headers.get("X-API-Key"):
                self.send_value(400, {"success": False, "message": "unexpected auth"})
                return
            self.store.auto_setup_calls += 1
            self.send_value(
                200,
                {
                    "success": True,
                    "message": "Auto-setup successful",
                    "user": {"id": "lite-user", "tenant_id": 1},
                    "active_tenant": {"id": 1, "name": self.store.tenant_name},
                    "memberships": [
                        {"tenant_id": 1, "tenant_name": self.store.tenant_name, "role": "owner"}
                    ],
                    "token": self.store.owner_token,
                    "refresh_token": "refresh-token-must-never-be-printed",
                },
            )
            return
        if path == f"/api/v1/tenants/{self.store.tenant_id}/api-keys":
            if not self.require_owner():
                return
            payload = self.read_json()
            self.store.create_payloads.append(dict(payload))
            key_id = self.store.next_key_id
            self.store.next_key_id += 1
            token = f"sk-created-secret-{key_id}"
            row = {
                "id": key_id,
                "scope_type": "tenant",
                "name": payload["name"],
                "api_key": token,
                "full_access": bool(payload["full_access"]),
                "knowledge_base_ids": []
                if payload["full_access"]
                else list(payload["knowledge_base_ids"]),
                "capabilities": []
                if payload["full_access"]
                else list(payload["capabilities"]),
                "expires_at": datetime.fromtimestamp(
                    int(payload["expires_at_unix"]),
                    timezone.utc,
                ).isoformat().replace("+00:00", "Z"),
            }
            self.store.api_keys.append(row)
            response = dict(row)
            # Reproduce v0.7.2 with SYSTEM_AES_KEY: the create response struct
            # may contain ciphertext, while data.token is the plaintext.
            response["api_key"] = f"enc:v1:ciphertext-{key_id}"
            response["token"] = token
            self.ok(response, status=201)
            return
        if path == "/api/v1/knowledge-search":
            payload = self.read_json()
            key = self.current_key()
            if key is None:
                self.send_value(401, {"success": False, "error": {"message": "unauthorized"}})
                return
            requested = {str(item) for item in payload.get("knowledge_base_ids", [])}
            allowed = {str(item) for item in key["knowledge_base_ids"]}
            permitted = key["full_access"] or (
                "retrieve" in key["capabilities"] and requested and requested.issubset(allowed)
            )
            if not permitted:
                self.store.forbidden_search_calls += 1
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
            self.store.allowed_search_calls += 1
            kb_id = next(iter(requested))
            self.ok(
                [
                    {
                        "id": f"chunk-{kb_id}",
                        "knowledge_base_id": kb_id,
                        "content": "fake result",
                        "score": 1.0,
                    }
                ]
            )
            return
        if path == "/api/v1/knowledge-bases":
            self.read_json()
            key = self.current_key()
            if key is not None and not key["full_access"]:
                if self.store.allow_scoped_write:
                    self.ok({"id": "should-not-exist"}, status=201)
                else:
                    self.store.forbidden_write_calls += 1
                    self.send_value(
                        403,
                        {
                            "success": False,
                            "error": {"message": "API key scope does not allow this operation"},
                        },
                    )
                return
        self.send_value(404, {"success": False, "message": path})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path_only()
        prefix = f"/api/v1/tenants/{self.store.tenant_id}/api-keys/"
        if path.startswith(prefix):
            if not self.require_owner():
                return
            key_id = path.removeprefix(prefix)
            self.store.delete_ids.append(key_id)
            before = len(self.store.api_keys)
            self.store.api_keys = [
                row for row in self.store.api_keys if str(row["id"]) != key_id
            ]
            if len(self.store.api_keys) == before:
                self.send_value(404, {"success": False, "message": "not found"})
            else:
                self.send_value(200, {"success": True})
            return
        self.send_value(404, {"success": False, "message": path})


@contextlib.contextmanager
def fake_lite_server() -> Any:
    store = LiteStore()
    server = ThreadingHTTPServer(("127.0.0.1", 0), LiteHandler)
    server.store = store  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield store, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def runtime_receipt(path: Path, base_url: str, *, duplicate: bool = False) -> None:
    ids = ["kb-staff", "kb-customer", "kb-policy", "kb-boundary"]
    if duplicate:
        ids[-1] = ids[0]
    path.write_text(
        json.dumps(
            {
                "status": "passed",
                "base_url": base_url,
                "tenant_partition": "runtime",
                "tenant": {"id": "1", "name": "WeKnora Lite"},
                "knowledge_bases": {
                    key: {"id": kb_id, "name": key}
                    for key, kb_id in zip(RUNTIME_KB_KEYS, ids)
                },
                "retrieval_smoke_tests": [
                    {
                        "name": "staff-course",
                        "query": "秀域品牌的业务板块有哪些？",
                        "knowledge_base_ids": ["kb-staff"],
                        "expected": "non_empty",
                        "result_count": 1,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_main(*argv: str) -> Tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = lite_provision_main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class LiteProvisionContractTest(unittest.TestCase):
    def test_migration_key_is_short_lived_private_idempotent_and_never_printed(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            secret = Path(raw) / "migration.json"
            before = int(time.time())
            code, stdout, stderr = run_main(
                "create-migration",
                "--base-url",
                base_url,
                "--expires-minutes",
                "120",
                "--output",
                str(secret),
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
            saved = json.loads(secret.read_text(encoding="utf-8"))
            token = saved["key"]["token"]
            self.assertTrue(token.startswith("sk-"))
            self.assertNotIn(token, stdout + stderr)
            self.assertNotIn(store.owner_token, stdout + stderr)
            self.assertIn('"token_values_printed": false', stdout)
            self.assertEqual(len(store.create_payloads), 1)
            payload = store.create_payloads[0]
            self.assertIs(payload["full_access"], True)
            self.assertEqual(payload["knowledge_base_ids"], [])
            self.assertEqual(payload["capabilities"], [])
            self.assertGreaterEqual(payload["expires_at_unix"], before + 119 * 60)
            self.assertLessEqual(payload["expires_at_unix"], before + 121 * 60)

            code, stdout, stderr = run_main(
                "create-migration",
                "--base-url",
                base_url,
                "--expires-minutes",
                "120",
                "--output",
                str(secret),
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(len(store.create_payloads), 1)
            self.assertTrue(json.loads(stdout)["key"]["reused"])
            self.assertNotIn(token, stdout + stderr)

    def test_revoke_is_idempotent_and_scrubs_plaintext(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            secret = Path(raw) / "migration.json"
            code, _, stderr = run_main(
                "create-migration", "--base-url", base_url, "--output", str(secret)
            )
            self.assertEqual(code, 0, stderr)
            token = json.loads(secret.read_text(encoding="utf-8"))["key"]["token"]

            code, stdout, stderr = run_main(
                "revoke", "--base-url", base_url, "--secret", str(secret)
            )
            self.assertEqual(code, 0, stderr)
            self.assertNotIn(token, stdout + stderr)
            state = json.loads(secret.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "revoked")
            self.assertNotIn("token", state["key"])
            self.assertEqual(store.api_keys, [])
            self.assertEqual(len(store.delete_ids), 1)

            code, stdout, stderr = run_main(
                "revoke", "--base-url", base_url, "--secret", str(secret)
            )
            self.assertEqual(code, 0, stderr)
            self.assertTrue(json.loads(stdout)["already_absent"])
            self.assertEqual(len(store.delete_ids), 1)

    def test_runtime_key_is_exactly_four_kb_retrieve_and_contract_tested(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            receipt = folder / "runtime-receipt.json"
            secret = folder / "runtime.json"
            runtime_receipt(receipt, base_url)
            code, stdout, stderr = run_main(
                "create-runtime",
                "--base-url",
                base_url,
                "--runtime-receipt",
                str(receipt),
                "--output",
                str(secret),
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
            saved = json.loads(secret.read_text(encoding="utf-8"))
            token = saved["key"]["token"]
            self.assertNotIn(token, stdout + stderr)
            payload = store.create_payloads[0]
            self.assertIs(payload["full_access"], False)
            self.assertEqual(payload["capabilities"], ["retrieve"])
            self.assertEqual(
                payload["knowledge_base_ids"],
                ["kb-staff", "kb-customer", "kb-policy", "kb-boundary"],
            )
            self.assertEqual(len(set(payload["knowledge_base_ids"])), 4)
            self.assertGreaterEqual(store.allowed_search_calls, 1)
            self.assertGreaterEqual(store.forbidden_search_calls, 1)
            self.assertGreaterEqual(store.forbidden_write_calls, 1)
            verification = json.loads(stdout)["verification"]
            self.assertTrue(verification["out_of_scope_retrieval_forbidden"])
            self.assertTrue(verification["write_forbidden"])
            self.assertEqual(
                verification["listed_knowledge_base_ids"],
                ["kb-boundary", "kb-customer", "kb-policy", "kb-staff"],
            )

            code, stdout, stderr = run_main(
                "create-runtime",
                "--base-url",
                base_url,
                "--runtime-receipt",
                str(receipt),
                "--output",
                str(secret),
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(len(store.create_payloads), 1)
            self.assertTrue(json.loads(stdout)["key"]["reused"])

    def test_ambiguous_same_name_is_explicitly_rejected_without_leak(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            first = store.add_key(
                "lite-migration-full-access", full_access=True, token="sk-first-secret"
            )
            second = store.add_key(
                "lite-migration-full-access", full_access=True, token="sk-second-secret"
            )
            code, stdout, stderr = run_main(
                "create-migration",
                "--base-url",
                base_url,
                "--output",
                str(Path(raw) / "migration.json"),
            )
            self.assertEqual(code, 1)
            self.assertIn("ambiguous existing API key name", stderr)
            self.assertNotIn(first["api_key"], stdout + stderr)
            self.assertNotIn(second["api_key"], stdout + stderr)
            self.assertEqual(store.create_payloads, [])

    def test_failed_runtime_verification_revokes_new_key_and_scrubs_secret(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            store.allow_scoped_write = True
            folder = Path(raw)
            receipt = folder / "receipt.json"
            secret = folder / "runtime.json"
            runtime_receipt(receipt, base_url)
            code, stdout, stderr = run_main(
                "create-runtime",
                "--base-url",
                base_url,
                "--runtime-receipt",
                str(receipt),
                "--output",
                str(secret),
            )
            self.assertEqual(code, 1)
            self.assertIn("write rejection test unexpectedly succeeded", stderr)
            self.assertEqual(store.api_keys, [])
            self.assertEqual(len(store.delete_ids), 1)
            state = json.loads(secret.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "revoked_after_failed_verification")
            self.assertNotIn("token", state["key"])
            self.assertNotIn("sk-created-secret", stdout + stderr)

    def test_runtime_receipt_requires_four_distinct_kbs_without_audit_receipt(self) -> None:
        with fake_lite_server() as (store, base_url), tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            receipt = folder / "receipt.json"
            runtime_receipt(receipt, base_url, duplicate=True)
            code, _, stderr = run_main(
                "create-runtime",
                "--base-url",
                base_url,
                "--runtime-receipt",
                str(receipt),
                "--output",
                str(folder / "runtime.json"),
            )
            self.assertEqual(code, 1)
            self.assertIn("four distinct knowledge bases", stderr)
            self.assertEqual(store.create_payloads, [])

    def test_auto_setup_refuses_non_loopback_before_network_access(self) -> None:
        with self.assertRaisesRegex(ImportFailure, "localhost"):
            auto_setup("https://weknora.example.com")

    def test_out_of_scope_probe_cannot_collide_with_receipt_ids(self) -> None:
        self.assertNotIn(
            OUT_OF_SCOPE_PROBE_ID,
            {"kb-staff", "kb-customer", "kb-policy", "kb-boundary"},
        )


if __name__ == "__main__":
    unittest.main()
