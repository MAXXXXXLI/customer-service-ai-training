#!/usr/bin/env python3
"""Provision and retire WeKnora v0.7.2 Lite migration/runtime API keys.

The Lite auto-setup endpoint is intentionally only called through an explicit
loopback URL.  Its Owner JWT remains in memory; API-key plaintext is written
only to an atomic ``0600`` secret file and is never included in console output.

Typical lifecycle::

    python3 lite_provision.py create-migration --output /secure/migration.json
    # use migration.json's token for setup_models.py and import_bundle.py
    python3 lite_provision.py create-runtime --runtime-receipt import_receipt.runtime.json
    python3 lite_provision.py revoke --secret /secure/migration.json
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import stat
import sys
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from import_bundle import (
    APIError,
    DEFAULT_RECEIPT_RUNTIME,
    EXPECTED_COMMIT,
    EXPECTED_VERSION,
    ImportFailure,
    WeKnoraClient,
)


MIGRATION_DIR = Path(__file__).resolve().parent
DEFAULT_MIGRATION_SECRET = MIGRATION_DIR / "import_state.lite_migration_secret.json"
DEFAULT_RUNTIME_SECRET = MIGRATION_DIR / "runtime_access_keys.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
RUNTIME_KB_KEYS: Tuple[str, ...] = (
    "staff_courses",
    "customer_approved",
    "safety_policy",
    "safety_boundary",
)
OUT_OF_SCOPE_PROBE_ID = "lite-provision-out-of-scope-probe"


@dataclass(frozen=True)
class OwnerSession:
    client: WeKnoraClient
    tenant: Dict[str, str]
    server: Dict[str, Any]


@dataclass(frozen=True)
class KeyMaterial:
    row: Dict[str, Any]
    token: str
    created: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_loopback_base_url(value: str) -> str:
    """Return a canonical base URL, rejecting any non-loopback authority."""

    raw = str(value or "").strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port  # Force validation of a malformed port.
    except ValueError as exc:
        raise ImportFailure("invalid WeKnora loopback URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ImportFailure("WeKnora URL must use http or https")
    if parsed.username or parsed.password:
        raise ImportFailure("WeKnora URL must not contain user information")
    if (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ImportFailure(
            "Lite auto-setup is unauthenticated; run this command on the server "
            "and use localhost/127.0.0.1/::1"
        )
    if parsed.query or parsed.fragment or parsed.path.rstrip("/") not in {"", "/api/v1"}:
        raise ImportFailure("WeKnora URL must be a loopback origin or end in /api/v1")
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    authority = host + (f":{port}" if port is not None else "")
    return f"{parsed.scheme}://{authority}"


def envelope_data(payload: Any, context: str) -> Any:
    """Decode the v0.7.2 success envelope without echoing response payloads."""

    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ImportFailure(f"{context} returned an invalid success envelope")
    return payload.get("data")


def list_data(payload: Any, context: str) -> List[Dict[str, Any]]:
    value = envelope_data(payload, context)
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        return [dict(row) for row in value]
    if (
        isinstance(value, dict)
        and isinstance(value.get("data"), list)
        and all(isinstance(row, dict) for row in value["data"])
    ):
        return [dict(row) for row in value["data"]]
    raise ImportFailure(f"{context} returned an unexpected list payload")


def parse_rfc3339_unix(value: Any, field: str = "expires_at") -> int:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ImportFailure(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ImportFailure(f"{field} must include a timezone")
    return int(parsed.timestamp())


def _plain_api_key(value: Any) -> str:
    token = str(value or "").strip()
    # v0.7.2 generates tenant keys with this prefix.  Treat ciphertext,
    # redaction placeholders, and arbitrary values as unavailable plaintext.
    return token if token.startswith("sk-") else ""


def _secret_mode_is_private(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) == 0o600


def read_secret_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    if not _secret_mode_is_private(path):
        raise ImportFailure(f"secret file permissions must be 0600: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ImportFailure(f"secret file must contain a JSON object: {path}")
    return value


def write_secret_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _current_tenant(client: WeKnoraClient) -> Dict[str, str]:
    data = envelope_data(client.request("GET", "/auth/me"), "current tenant")
    if not isinstance(data, dict) or not isinstance(data.get("tenant"), dict):
        raise ImportFailure("current tenant returned an invalid payload")
    tenant = data["tenant"]
    tenant_id = str(tenant.get("id", "")).strip()
    tenant_name = str(tenant.get("name", "")).strip()
    if not tenant_id or not tenant_name:
        raise ImportFailure("current tenant response is missing id or name")
    return {"id": tenant_id, "name": tenant_name}


def _verify_server(client: WeKnoraClient) -> Dict[str, Any]:
    payload = client.request("GET", "/system/info")
    # v0.7.2's SystemHandler predates the repository-wide {success,data}
    # envelope and returns {code: 0, msg: "success", data: {...}}.  Accept
    # exactly that documented legacy success shape for this endpoint only;
    # all provisioning/mutation endpoints remain on the strict envelope.
    if isinstance(payload, dict) and payload.get("success") is True:
        info = payload.get("data")
    elif isinstance(payload, dict) and payload.get("code") == 0:
        info = payload.get("data")
    else:
        raise ImportFailure("system info returned an invalid success envelope")
    if not isinstance(info, dict):
        raise ImportFailure("system info returned an invalid payload")
    version = str(info.get("version", "")).strip()
    commit = str(info.get("commit_id", "")).strip()
    edition = str(info.get("edition", "")).strip().lower()
    version_ok = version.lstrip("v") == EXPECTED_VERSION.lstrip("v")
    commit_ok = not commit or EXPECTED_COMMIT.startswith(commit) or commit.startswith(EXPECTED_COMMIT)
    if not version_ok or not commit_ok:
        raise ImportFailure(
            f"server version mismatch; expected {EXPECTED_VERSION}/{EXPECTED_COMMIT[:12]}"
        )
    if edition != "lite":
        raise ImportFailure("server is not the WeKnora Lite edition")
    return {"version": version, "commit_id": commit, "edition": edition}


def auto_setup(base_url: str, timeout: float = 30.0) -> OwnerSession:
    """Obtain an in-memory Owner session from Lite's direct login response."""

    canonical = normalize_loopback_base_url(base_url)
    anonymous = WeKnoraClient(canonical, timeout=timeout)
    payload = anonymous.request(
        "POST",
        "/auth/auto-setup",
        json_body={},
        accepted=(200,),
    )
    # AutoSetup is deliberately not wrapped in {success,data} in v0.7.2.
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ImportFailure("Lite auto-setup returned an invalid response")
    owner_jwt = str(payload.get("token", "")).strip()
    active = payload.get("active_tenant")
    memberships = payload.get("memberships")
    if not owner_jwt or not isinstance(active, dict) or not isinstance(memberships, list):
        raise ImportFailure("Lite auto-setup omitted the Owner token or active tenant")
    tenant = {
        "id": str(active.get("id", "")).strip(),
        "name": str(active.get("name", "")).strip(),
    }
    if not tenant["id"] or not tenant["name"]:
        raise ImportFailure("Lite auto-setup returned an incomplete active tenant")
    is_owner = any(
        isinstance(row, dict)
        and str(row.get("tenant_id", "")).strip() == tenant["id"]
        and str(row.get("role", "")).strip().casefold() == "owner"
        for row in memberships
    )
    if not is_owner:
        raise ImportFailure("Lite auto-setup did not return Owner membership")
    owner = WeKnoraClient(canonical, timeout=timeout, bearer_token=owner_jwt)
    if _current_tenant(owner) != tenant:
        raise ImportFailure("Owner JWT tenant differs from the auto-setup active tenant")
    server = _verify_server(owner)
    return OwnerSession(client=owner, tenant=tenant, server=server)


def list_api_keys(owner: OwnerSession) -> List[Dict[str, Any]]:
    return list_data(
        owner.client.request("GET", f"/tenants/{owner.tenant['id']}/api-keys"),
        "list tenant API keys",
    )


def migration_key_spec(name: str, expires_at_unix: int) -> Dict[str, Any]:
    return {
        "kind": "migration",
        "name": name,
        "full_access": True,
        "knowledge_base_ids": [],
        "capabilities": [],
        "expires_at_unix": int(expires_at_unix),
    }


def _validate_runtime_receipt(
    receipt: Mapping[str, Any], base_url: str, tenant: Mapping[str, str]
) -> Tuple[List[str], Dict[str, Any]]:
    if receipt.get("status") != "passed" or receipt.get("tenant_partition") != "runtime":
        raise ImportFailure("runtime receipt is missing, not passed, or not the runtime partition")
    if str(receipt.get("base_url", "")).rstrip("/") != base_url.rstrip("/"):
        raise ImportFailure("runtime receipt belongs to a different WeKnora server")
    receipt_tenant = receipt.get("tenant")
    if not isinstance(receipt_tenant, dict) or str(receipt_tenant.get("id", "")) != tenant["id"]:
        raise ImportFailure("runtime receipt belongs to another tenant")
    knowledge_bases = receipt.get("knowledge_bases")
    if not isinstance(knowledge_bases, dict):
        raise ImportFailure("runtime receipt contains no knowledge-base map")
    ids: List[str] = []
    for key in RUNTIME_KB_KEYS:
        row = knowledge_bases.get(key)
        kb_id = str(row.get("id", "")).strip() if isinstance(row, dict) else ""
        if not kb_id:
            raise ImportFailure(f"runtime receipt is missing knowledge base {key}")
        ids.append(kb_id)
    if len(set(ids)) != len(RUNTIME_KB_KEYS):
        raise ImportFailure("runtime receipt does not contain four distinct knowledge bases")
    return ids, dict(receipt)


def runtime_key_spec(
    receipt: Mapping[str, Any],
    base_url: str,
    tenant: Mapping[str, str],
    name: str,
    expires_at_unix: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ids, checked_receipt = _validate_runtime_receipt(receipt, base_url, tenant)
    return (
        {
            "kind": "runtime",
            "name": name,
            "full_access": False,
            "knowledge_base_ids": ids,
            "capabilities": ["retrieve"],
            "expires_at_unix": int(expires_at_unix),
        },
        checked_receipt,
    )


def public_key_payload(spec: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "name": spec["name"],
        "full_access": bool(spec["full_access"]),
        "knowledge_base_ids": list(spec["knowledge_base_ids"]),
        "capabilities": list(spec["capabilities"]),
        "expires_at_unix": int(spec["expires_at_unix"]),
    }


def validate_key_shape(
    row: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    require_exact_expiry: bool = False,
) -> int:
    if not str(row.get("id", "")).strip():
        raise ImportFailure(f"{spec['name']}: API key has no ID")
    if str(row.get("name", "")) != str(spec["name"]):
        raise ImportFailure(f"{spec['name']}: API key name differs")
    if str(row.get("scope_type", "")).strip().lower() != "tenant":
        raise ImportFailure(f"{spec['name']}: scope_type must be tenant")
    if bool(row.get("full_access")) != bool(spec["full_access"]):
        raise ImportFailure(f"{spec['name']}: full_access differs from the requested shape")
    actual_ids = [str(item) for item in (row.get("knowledge_base_ids") or [])]
    expected_ids = [str(item) for item in spec["knowledge_base_ids"]]
    actual_caps = [str(item) for item in (row.get("capabilities") or [])]
    expected_caps = [str(item) for item in spec["capabilities"]]
    if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(set(actual_ids)):
        raise ImportFailure(f"{spec['name']}: knowledge-base allow-list is not exact")
    if set(actual_caps) != set(expected_caps) or len(actual_caps) != len(set(actual_caps)):
        raise ImportFailure(f"{spec['name']}: capabilities are not exact")
    if not spec["full_access"] and len(actual_ids) != len(RUNTIME_KB_KEYS):
        raise ImportFailure(f"{spec['name']}: runtime key must allow exactly four KBs")
    expiry = parse_rfc3339_unix(row.get("expires_at"))
    now = int(time.time())
    maximum = int(spec["expires_at_unix"])
    if expiry <= now + 60:
        raise ImportFailure(f"{spec['name']}: API key is expired or has under 60 seconds left")
    if expiry > maximum or (require_exact_expiry and expiry != maximum):
        raise ImportFailure(f"{spec['name']}: API key expiry exceeds the requested limit")
    return expiry


def _validate_saved_secret(
    saved: Mapping[str, Any], owner: OwnerSession, spec: Mapping[str, Any]
) -> Mapping[str, Any]:
    if not saved:
        return {}
    if saved.get("schema_version") != 1:
        raise ImportFailure("existing secret file uses an unsupported schema")
    if str(saved.get("server", "")).rstrip("/") != owner.client.base_url:
        raise ImportFailure("existing secret file belongs to another server")
    saved_tenant = saved.get("tenant")
    if not isinstance(saved_tenant, dict) or str(saved_tenant.get("id", "")) != owner.tenant["id"]:
        raise ImportFailure("existing secret file belongs to another tenant")
    if saved.get("kind") != spec["kind"]:
        raise ImportFailure("existing secret file is for another key kind")
    key = saved.get("key")
    if not isinstance(key, dict) or str(key.get("name", "")) != str(spec["name"]):
        raise ImportFailure("existing secret file is for another API key name")
    return key


def _save_active_secret(
    path: Path,
    owner: OwnerSession,
    spec: Mapping[str, Any],
    row: Mapping[str, Any],
    token: str,
) -> None:
    if not _plain_api_key(token):
        raise ImportFailure("refusing to persist a non-v0.7.2 API key token")
    write_secret_json(
        path,
        {
            "schema_version": 1,
            "status": "active",
            "kind": spec["kind"],
            "server": owner.client.base_url,
            "tenant": owner.tenant,
            "key": {
                "id": str(row["id"]),
                "name": spec["name"],
                "token": token,
                "full_access": bool(spec["full_access"]),
                "knowledge_base_ids": list(spec["knowledge_base_ids"]),
                "capabilities": list(spec["capabilities"]),
                "expires_at": row.get("expires_at"),
            },
            "updated_at": utc_now(),
            "warning": "Secret file: chmod 0600; never commit, print, or copy into browser code.",
        },
    )


def _token_for_existing(
    row: Mapping[str, Any], saved_key: Mapping[str, Any], context: str
) -> str:
    listed = _plain_api_key(row.get("api_key"))
    saved = _plain_api_key(saved_key.get("token"))
    if saved and str(saved_key.get("id", "")) != str(row.get("id", "")):
        raise ImportFailure(f"{context}: saved token belongs to another key ID")
    if listed and saved and not hmac.compare_digest(listed, saved):
        raise ImportFailure(f"{context}: saved token differs from the server value")
    token = saved or listed
    if not token:
        raise ImportFailure(
            f"{context}: no reusable plaintext token; revoke the named key and create it again"
        )
    return token


def _delete_key(owner: OwnerSession, key_id: str) -> None:
    owner.client.request(
        "DELETE",
        f"/tenants/{owner.tenant['id']}/api-keys/{key_id}",
        accepted=(200,),
    )


def ensure_api_key(
    owner: OwnerSession, spec: Mapping[str, Any], output: Path
) -> KeyMaterial:
    """Create/reuse one unambiguous named key and persist its secret safely."""

    existing = list_api_keys(owner)
    matches = [row for row in existing if str(row.get("name", "")) == spec["name"]]
    if len(matches) > 1:
        raise ImportFailure(f"ambiguous existing API key name: {spec['name']}")
    saved = read_secret_json(output)
    saved_key = _validate_saved_secret(saved, owner, spec) if saved else {}
    if matches:
        row = matches[0]
        validate_key_shape(row, spec)
        token = _token_for_existing(row, saved_key, str(spec["name"]))
        _save_active_secret(output, owner, spec, row, token)
        return KeyMaterial(dict(row), token, False)

    if saved and saved.get("status") == "active":
        raise ImportFailure("active secret file names a key that is missing from the server")

    preexisting_ids = {str(row.get("id", "")) for row in existing}
    created_id = ""
    created_token = ""
    row: Dict[str, Any]
    try:
        try:
            created = envelope_data(
                owner.client.request(
                    "POST",
                    f"/tenants/{owner.tenant['id']}/api-keys",
                    json_body=public_key_payload(spec),
                    accepted=(201,),
                ),
                f"create API key {spec['name']}",
            )
            if not isinstance(created, dict) or not str(created.get("id", "")).strip():
                raise ImportFailure(f"create API key returned no ID: {spec['name']}")
            created_id = str(created["id"])
            created_token = _plain_api_key(created.get("token"))
            if not created_token:
                raise ImportFailure(f"create API key returned no plaintext token: {spec['name']}")
        except (APIError, ImportFailure) as create_error:
            # A response can be lost after a successful commit.  v0.7.2 list
            # returns the decrypted api_key, so safely discover one new row.
            discovered = list_api_keys(owner)
            candidates = [
                candidate
                for candidate in discovered
                if str(candidate.get("name", "")) == spec["name"]
                and str(candidate.get("id", "")) not in preexisting_ids
            ]
            if len(candidates) != 1:
                if len(candidates) > 1:
                    raise ImportFailure(
                        f"ambiguous API key creation: multiple new keys named {spec['name']}"
                    ) from create_error
                raise
            row = candidates[0]
            created_id = str(row.get("id", ""))
            created_token = _plain_api_key(row.get("api_key"))
            if not created_token:
                _delete_key(owner, created_id)
                created_id = ""
                raise ImportFailure(
                    f"could not recover plaintext after ambiguous create: {spec['name']}"
                ) from create_error

        refreshed = list_api_keys(owner)
        matches = [row for row in refreshed if str(row.get("name", "")) == spec["name"]]
        if len(matches) != 1 or str(matches[0].get("id", "")) != created_id:
            raise ImportFailure(f"concurrent or ambiguous API key creation: {spec['name']}")
        row = matches[0]
        validate_key_shape(row, spec, require_exact_expiry=True)
        listed_token = _plain_api_key(row.get("api_key"))
        if listed_token and not hmac.compare_digest(listed_token, created_token):
            raise ImportFailure(f"created API key token mismatch: {spec['name']}")
        _save_active_secret(output, owner, spec, row, created_token)
        return KeyMaterial(dict(row), created_token, True)
    except Exception:
        if created_id:
            try:
                _delete_key(owner, created_id)
            except (APIError, ImportFailure) as rollback_error:
                raise ImportFailure(
                    f"API key provisioning failed and rollback of key {created_id} failed"
                ) from rollback_error
        raise


def _verify_key_tenant(base_url: str, token: str, expected_tenant: Mapping[str, str], timeout: float) -> None:
    tenant = _current_tenant(WeKnoraClient(base_url, token, timeout=timeout))
    if tenant != dict(expected_tenant):
        raise ImportFailure("API key authenticates into a different tenant")


def verify_migration_key(
    base_url: str,
    token: str,
    expected_tenant: Mapping[str, str],
    timeout: float,
) -> Dict[str, Any]:
    client = WeKnoraClient(base_url, token, timeout=timeout)
    _verify_key_tenant(base_url, token, expected_tenant, timeout)
    visible = list_data(client.request("GET", "/knowledge-bases"), "full-access KB listing")
    return {
        "tenant_id": expected_tenant["id"],
        "authentication": "passed",
        "full_access_listing": "passed",
        "visible_knowledge_base_count": len(visible),
    }


def _expect_forbidden(
    client: WeKnoraClient, method: str, path: str, body: Mapping[str, Any], context: str
) -> None:
    try:
        client.request(method, path, json_body=dict(body))
    except APIError as exc:
        if exc.status == 403:
            return
        raise ImportFailure(f"{context} returned HTTP {exc.status}, expected 403") from exc
    raise ImportFailure(f"{context} unexpectedly succeeded")


def _positive_probe(receipt: Mapping[str, Any], allowed_ids: Sequence[str]) -> Tuple[str, List[str]]:
    allowed = set(allowed_ids)
    rows = receipt.get("retrieval_smoke_tests")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or row.get("expected") != "non_empty":
                continue
            query = str(row.get("query", "")).strip()
            kb_ids = [str(item).strip() for item in row.get("knowledge_base_ids", [])]
            if query and kb_ids and set(kb_ids).issubset(allowed):
                return query, kb_ids
    return "秀域品牌的业务板块有哪些？", [str(allowed_ids[0])]


def verify_runtime_key(
    base_url: str,
    token: str,
    expected_tenant: Mapping[str, str],
    spec: Mapping[str, Any],
    receipt: Mapping[str, Any],
    timeout: float,
) -> Dict[str, Any]:
    client = WeKnoraClient(base_url, token, timeout=timeout)
    _verify_key_tenant(base_url, token, expected_tenant, timeout)
    listed = list_data(client.request("GET", "/knowledge-bases"), "list scoped KBs")
    listed_ids = {str(row.get("id", "")) for row in listed}
    allowed_ids = [str(item) for item in spec["knowledge_base_ids"]]
    if listed_ids != set(allowed_ids):
        raise ImportFailure("runtime key KB listing is not the exact four-KB allow-list")

    query, positive_ids = _positive_probe(receipt, allowed_ids)
    rows = envelope_data(
        client.request(
            "POST",
            "/knowledge-search",
            json_body={"query": query, "knowledge_base_ids": positive_ids},
        ),
        "allowed retrieval test",
    )
    if not isinstance(rows, list) or not rows:
        raise ImportFailure("allowed retrieval test returned no results")
    if any(
        not isinstance(row, dict)
        or str(row.get("knowledge_base_id", "")) not in set(positive_ids)
        for row in rows
    ):
        raise ImportFailure("allowed retrieval test escaped its requested KB scope")

    forbidden_probe_id = OUT_OF_SCOPE_PROBE_ID
    while forbidden_probe_id in set(allowed_ids):
        forbidden_probe_id += "-outside"
    _expect_forbidden(
        client,
        "POST",
        "/knowledge-search",
        {"query": "越权测试", "knowledge_base_ids": [forbidden_probe_id]},
        "out-of-scope retrieval test",
    )
    _expect_forbidden(
        client,
        "POST",
        "/knowledge-bases",
        {"name": "MUST-NOT-BE-CREATED", "type": "document"},
        "write rejection test",
    )
    return {
        "tenant_id": expected_tenant["id"],
        "listed_knowledge_base_ids": sorted(listed_ids),
        "allowed_retrieval_result_count": len(rows),
        "out_of_scope_retrieval_forbidden": True,
        "write_forbidden": True,
    }


def _rollback_verified_key(
    owner: OwnerSession, material: KeyMaterial, output: Path, reason: str
) -> None:
    if not material.created:
        return
    key_id = str(material.row["id"])
    rollback_failed = False
    try:
        _delete_key(owner, key_id)
    except (APIError, ImportFailure):
        rollback_failed = True
    write_secret_json(
        output,
        {
            "schema_version": 1,
            "status": (
                "revocation_failed_after_failed_verification"
                if rollback_failed
                else "revoked_after_failed_verification"
            ),
            "server": owner.client.base_url,
            "tenant": owner.tenant,
            "key": {"id": key_id, "name": material.row.get("name")},
            "updated_at": utc_now(),
            "reason": reason,
        },
    )
    if rollback_failed:
        raise ImportFailure(
            f"verification failed and rollback of new API key {key_id} failed; rerun revoke"
        )


def provision_with_verification(
    owner: OwnerSession,
    spec: Mapping[str, Any],
    output: Path,
    verifier: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    material = ensure_api_key(owner, spec, output)
    try:
        verification = verifier(material.token)
    except (APIError, ImportFailure, KeyError, ValueError) as exc:
        _rollback_verified_key(owner, material, output, "verification failed")
        raise exc
    expiry = validate_key_shape(material.row, spec)
    return {
        "status": "passed",
        "kind": spec["kind"],
        "server": owner.client.base_url,
        "tenant": owner.tenant,
        "server_version": owner.server,
        "secret_file": str(output.resolve()),
        "key": {
            "id": str(material.row["id"]),
            "name": spec["name"],
            "reused": not material.created,
            "full_access": bool(spec["full_access"]),
            "knowledge_base_ids": list(spec["knowledge_base_ids"]),
            "capabilities": list(spec["capabilities"]),
            "expires_at_unix": expiry,
        },
        "verification": verification,
        "token_values_printed": False,
    }


def revoke_secret(owner: OwnerSession, secret_path: Path) -> Dict[str, Any]:
    state = read_secret_json(secret_path)
    if not state:
        raise ImportFailure(f"secret file does not exist: {secret_path}")
    if str(state.get("server", "")).rstrip("/") != owner.client.base_url:
        raise ImportFailure("secret file belongs to another server")
    tenant = state.get("tenant")
    if not isinstance(tenant, dict) or str(tenant.get("id", "")) != owner.tenant["id"]:
        raise ImportFailure("secret file belongs to another tenant")
    key = state.get("key")
    if not isinstance(key, dict):
        raise ImportFailure("secret file contains no key metadata")
    key_id = str(key.get("id", "")).strip()
    key_name = str(key.get("name", "")).strip()
    if not key_id or not key_name:
        raise ImportFailure("secret file key metadata is incomplete")

    rows = list_api_keys(owner)
    by_id = [row for row in rows if str(row.get("id", "")) == key_id]
    if len(by_id) > 1:
        raise ImportFailure(f"ambiguous API key ID in server response: {key_id}")
    already_absent = not by_id
    if by_id:
        if str(by_id[0].get("name", "")) != key_name:
            raise ImportFailure("secret key ID now belongs to a differently named key")
        _delete_key(owner, key_id)
    if any(str(row.get("id", "")) == key_id for row in list_api_keys(owner)):
        raise ImportFailure("API key is still present after revocation")

    write_secret_json(
        secret_path,
        {
            "schema_version": 1,
            "status": "revoked",
            "kind": state.get("kind"),
            "server": owner.client.base_url,
            "tenant": owner.tenant,
            "key": {"id": key_id, "name": key_name},
            "revoked_at": utc_now(),
            "warning": "The plaintext token was removed from this file.",
        },
    )
    return {
        "status": "revoked",
        "server": owner.client.base_url,
        "tenant": owner.tenant,
        "secret_file": str(secret_path.resolve()),
        "key": {"id": key_id, "name": key_name},
        "already_absent": already_absent,
        "token_values_printed": False,
    }


def _safe_error(exc: BaseException) -> str:
    # APIError.__str__ includes the server payload; a malicious/misconfigured
    # endpoint could put plaintext credentials there, so never render it.
    if isinstance(exc, APIError):
        return f"HTTP {exc.status} {exc.method} {exc.url}"
    return str(exc)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WEKNORA_URL", DEFAULT_BASE_URL),
        help="loopback WeKnora origin; run this utility on the Lite server",
    )
    parser.add_argument("--http-timeout", type=float, default=30.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    migration = commands.add_parser("create-migration", help="create/reuse a short full-access key")
    _add_common_arguments(migration)
    migration.add_argument("--name", default="lite-migration-full-access")
    migration.add_argument("--expires-minutes", type=int, default=120)
    migration.add_argument("--output", type=Path, default=DEFAULT_MIGRATION_SECRET)

    runtime = commands.add_parser("create-runtime", help="create/reuse and test the four-KB key")
    _add_common_arguments(runtime)
    runtime.add_argument("--runtime-receipt", type=Path, default=DEFAULT_RECEIPT_RUNTIME)
    runtime.add_argument("--name", default="lite-runtime-four-kb-retrieve")
    runtime.add_argument("--expires-days", type=int, default=90)
    runtime.add_argument("--output", type=Path, default=DEFAULT_RUNTIME_SECRET)

    revoke = commands.add_parser("revoke", help="revoke the exact key recorded in a secret file")
    _add_common_arguments(revoke)
    revoke.add_argument("--secret", type=Path, default=DEFAULT_MIGRATION_SECRET)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.http_timeout <= 0:
            raise ImportFailure("--http-timeout must be positive")
        owner = auto_setup(args.base_url, args.http_timeout)
        if args.command == "create-migration":
            if args.expires_minutes < 5 or args.expires_minutes > 1440:
                raise ImportFailure("--expires-minutes must be between 5 and 1440")
            spec = migration_key_spec(
                args.name,
                int(time.time()) + args.expires_minutes * 60,
            )
            result = provision_with_verification(
                owner,
                spec,
                args.output.resolve(),
                lambda token: verify_migration_key(
                    owner.client.base_url,
                    token,
                    owner.tenant,
                    args.http_timeout,
                ),
            )
        elif args.command == "create-runtime":
            if args.expires_days < 1 or args.expires_days > 365:
                raise ImportFailure("--expires-days must be between 1 and 365")
            receipt = json.loads(args.runtime_receipt.read_text(encoding="utf-8"))
            if not isinstance(receipt, dict):
                raise ImportFailure("runtime receipt must contain a JSON object")
            spec, checked_receipt = runtime_key_spec(
                receipt,
                owner.client.base_url,
                owner.tenant,
                args.name,
                int(time.time()) + args.expires_days * 86400,
            )
            result = provision_with_verification(
                owner,
                spec,
                args.output.resolve(),
                lambda token: verify_runtime_key(
                    owner.client.base_url,
                    token,
                    owner.tenant,
                    spec,
                    checked_receipt,
                    args.http_timeout,
                ),
            )
        else:
            result = revoke_secret(owner, args.secret.resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        APIError,
        ImportFailure,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"Lite provisioning failed: {_safe_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
