#!/usr/bin/env python3
"""Import the verified migration bundle into WeKnora v0.7.2 via REST.

The command is deliberately conservative:

* without ``--apply`` it only prints the local import plan;
* it refuses ambiguous or mismatched knowledge-base names;
* it refuses to adopt existing KBs unless explicitly authorised;
* every FAQ replace is preceded by an asynchronous dry-run;
* it patches and re-reads FAQ flags because v0.7.2 bulk import drops the
  ``is_recommended`` value for newly inserted entries;
* it writes an incremental state file and a final receipt, but never a secret.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from verify_bundle import BundleValidationError, validate_bundle


MIGRATION_DIR = Path(__file__).resolve().parent
DEFAULT_BUNDLE = MIGRATION_DIR / "bundle"
DEFAULT_STATE_RUNTIME = MIGRATION_DIR / "import_state.runtime.json"
DEFAULT_STATE_AUDIT = MIGRATION_DIR / "import_state.audit.json"
DEFAULT_RECEIPT_RUNTIME = MIGRATION_DIR / "import_receipt.runtime.json"
DEFAULT_RECEIPT_AUDIT = MIGRATION_DIR / "import_receipt.audit.json"
EXPECTED_VERSION = "v0.7.2"
EXPECTED_COMMIT = "3d5d8bfcdfeeea266b292b71cea616847af28d0f"
TERMINAL_DOCUMENT_STATES = {"completed", "failed", "cancelled"}
TERMINAL_FAQ_STATES = {"completed", "failed"}


class ImportFailure(RuntimeError):
    pass


class APIError(ImportFailure):
    def __init__(self, status: int, method: str, url: str, payload: Any) -> None:
        self.status = status
        self.method = method
        self.url = url
        self.payload = payload
        super().__init__(f"HTTP {status} {method} {url}: {payload!r}")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(str(temporary), str(path))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def immutable_bundle_snapshot(source: Path) -> Iterable[Path]:
    """Copy the source once, make the copy read-only, and import only that copy."""

    source = source.resolve()
    root = Path(tempfile.mkdtemp(prefix="weknora-import-snapshot-"))
    snapshot = root / "bundle"
    try:
        try:
            shutil.copytree(source, snapshot, symlinks=False)
            for path in snapshot.rglob("*"):
                path.chmod(0o500 if path.is_dir() else 0o400)
            snapshot.chmod(0o500)
        except (OSError, shutil.Error) as exc:
            raise ImportFailure(f"cannot create immutable bundle snapshot: {exc}") from exc
        yield snapshot
    finally:
        if snapshot.exists():
            try:
                snapshot.chmod(0o700)
                for path in snapshot.rglob("*"):
                    path.chmod(0o700 if path.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)


def envelope_data(payload: Any, context: str) -> Any:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ImportFailure(f"{context} returned an invalid success envelope: {payload!r}")
    return payload.get("data")


def flatten_page_data(value: Any, context: str) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        return value["data"]
    raise ImportFailure(f"{context} returned an unexpected list payload: {value!r}")


class WeKnoraClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 120.0,
        bearer_token: str = "",
    ) -> None:
        if api_key and bearer_token:
            raise ValueError("api_key and bearer_token are mutually exclusive")
        base = base_url.rstrip("/")
        if base.endswith("/api/v1"):
            base = base[: -len("/api/v1")]
        self.base_url = base
        self.api_root = base + "/api/v1"
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout = timeout

    def _url(self, path: str, api: bool, query: Optional[Sequence[Tuple[str, Any]]] = None) -> str:
        root = self.api_root if api else self.base_url
        url = root + (path if path.startswith("/") else "/" + path)
        if query:
            url += "?" + urllib.parse.urlencode(list(query), doseq=True)
        return url

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
        if body is not None and json_body is not None:
            raise ValueError("body and json_body are mutually exclusive")
        request_headers = {"Accept": "application/json"}
        if self.api_key:
            request_headers["X-API-Key"] = self.api_key
        elif self.bearer_token:
            request_headers["Authorization"] = f"Bearer {self.bearer_token}"
        if headers:
            request_headers.update(headers)
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json; charset=utf-8"
        url = self._url(path, api=api, query=query)
        request = urllib.request.Request(url, data=body, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            payload = self._decode(raw)
            raise APIError(status, method, url, payload) from exc
        except urllib.error.URLError as exc:
            raise ImportFailure(f"cannot reach WeKnora at {url}: {exc}") from exc
        payload = self._decode(raw)
        if status not in accepted:
            raise APIError(status, method, url, payload)
        return payload

    @staticmethod
    def _decode(raw: bytes) -> Any:
        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def upload_document(
        self,
        kb_id: str,
        path: Path,
        file_name: str,
        metadata: Mapping[str, str],
        tag_ids: Sequence[str],
        process_config: Mapping[str, Any],
    ) -> Any:
        boundary = "----weknora-migration-" + secrets.token_hex(16)
        chunks: List[bytes] = []

        def add_field(name: str, value: str) -> None:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )

        add_field("fileName", file_name)
        add_field("metadata", json.dumps(dict(metadata), ensure_ascii=False, separators=(",", ":")))
        add_field("enable_multimodel", "false")
        add_field("tag_ids", ",".join(tag_ids))
        add_field("channel", "api")
        add_field("process_config", json.dumps(process_config, ensure_ascii=False, separators=(",", ":")))
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("ascii"),
                b'Content-Disposition: form-data; name="file"; filename="document.md"\r\n',
                b"Content-Type: text/markdown; charset=utf-8\r\n\r\n",
                path.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode("ascii"),
            ]
        )
        return self.request(
            "POST",
            f"/knowledge-bases/{kb_id}/knowledge/file",
            body=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            accepted=(200, 201),
        )


def load_state(
    path: Path,
    bundle_version: str,
    bundle_manifest_sha256: str,
    base_url: str,
    scope: str,
    tenant_id: str,
) -> Dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "bundle_version": bundle_version,
            "bundle_manifest_sha256": bundle_manifest_sha256,
            "base_url": base_url.rstrip("/"),
            "tenant_partition": scope,
            "tenant_id": tenant_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "knowledge_bases": {},
            "documents": {},
            "faq_imports": {},
        }
    state = read_json(path)
    if state.get("bundle_version") != bundle_version:
        raise ImportFailure(
            f"state belongs to bundle {state.get('bundle_version')!r}, not {bundle_version!r}; "
            "do not mix migration versions"
        )
    if state.get("bundle_manifest_sha256") != bundle_manifest_sha256:
        raise ImportFailure("state belongs to different bundle content")
    if state.get("base_url", "").rstrip("/") != base_url.rstrip("/"):
        raise ImportFailure("state belongs to a different WeKnora server")
    if state.get("tenant_partition") != scope:
        raise ImportFailure(
            f"state belongs to tenant partition {state.get('tenant_partition')!r}, not {scope!r}"
        )
    if str(state.get("tenant_id", "")) != tenant_id:
        raise ImportFailure("state belongs to a different WeKnora tenant")
    return state


def save_state(path: Path, state: Dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json_atomic(path, state)


def ensure_server_version(
    client: WeKnoraClient,
    allow_version_mismatch: bool,
) -> Dict[str, Any]:
    health = client.request("GET", "/health", api=False, accepted=(200,))
    try:
        info_payload = client.request("GET", "/system/info", accepted=(200,))
        # v0.7.2 SystemHandler uses its legacy {code,msg,data} response while
        # the rest of the migration surface uses {success,data}.  Accept the
        # legacy shape only when code is exactly zero; never let
        # --allow-version-mismatch bypass an invalid success envelope.
        if isinstance(info_payload, dict) and info_payload.get("success") is True:
            info = info_payload.get("data")
        elif isinstance(info_payload, dict) and info_payload.get("code") == 0:
            info = info_payload.get("data")
        else:
            raise ImportFailure("system info returned an invalid success envelope")
        if not isinstance(info, dict):
            raise ImportFailure("system info returned an invalid payload")
    except APIError as exc:
        if exc.status not in {401, 403, 404}:
            raise
        info = {"unavailable": True, "reason": f"HTTP {exc.status}"}
    if isinstance(info, dict) and not info.get("unavailable"):
        version = str(info.get("version", ""))
        commit = str(info.get("commit_id", ""))
        version_ok = version.lstrip("v") == EXPECTED_VERSION.lstrip("v")
        commit_ok = not commit or EXPECTED_COMMIT.startswith(commit) or commit.startswith(EXPECTED_COMMIT)
        if not allow_version_mismatch and (not version_ok or not commit_ok):
            raise ImportFailure(
                f"server version mismatch: expected {EXPECTED_VERSION}/{EXPECTED_COMMIT[:12]}, "
                f"got {version!r}/{commit!r}"
            )
    return {"health": health, "system_info": info}


def get_current_tenant(client: WeKnoraClient) -> Dict[str, str]:
    data = envelope_data(client.request("GET", "/auth/me"), "current tenant")
    if not isinstance(data, dict) or not isinstance(data.get("tenant"), dict):
        raise ImportFailure(f"current tenant returned an invalid payload: {data!r}")
    tenant = data["tenant"]
    tenant_id = str(tenant.get("id", "")).strip()
    tenant_name = str(tenant.get("name", "")).strip()
    if not tenant_id or not tenant_name:
        raise ImportFailure("current tenant response is missing id or name")
    return {"id": tenant_id, "name": tenant_name}


def verify_tenant_partition(
    tenant: Mapping[str, str],
    scope: str,
    expected_tenant_id: str,
    peer_receipt: Path,
    bundle_version: str,
    bundle_manifest_sha256: str,
    base_url: str,
) -> None:
    if not expected_tenant_id:
        raise ImportFailure(
            "WEKNORA_EXPECTED_TENANT_ID (or --expected-tenant-id) is required for --apply"
        )
    if tenant["id"] != expected_tenant_id:
        raise ImportFailure(
            f"API key belongs to tenant {tenant['id']!r}, expected {expected_tenant_id!r}"
        )
    if scope == "audit" and not peer_receipt.is_file():
        raise ImportFailure(
            f"runtime receipt is required before audit import: {peer_receipt}"
        )
    if peer_receipt.is_file():
        peer = read_json(peer_receipt)
        expected_peer_scope = "audit" if scope == "runtime" else "runtime"
        if peer.get("status") != "passed":
            raise ImportFailure(f"peer receipt is not passed: {peer_receipt}")
        if peer.get("tenant_partition") != expected_peer_scope:
            raise ImportFailure(
                f"peer receipt partition is not {expected_peer_scope!r}: {peer_receipt}"
            )
        if peer.get("bundle_version") != bundle_version:
            raise ImportFailure(f"peer receipt belongs to a different bundle: {peer_receipt}")
        if peer.get("bundle_manifest_sha256") != bundle_manifest_sha256:
            raise ImportFailure(f"peer receipt belongs to different bundle content: {peer_receipt}")
        if str(peer.get("base_url", "")).rstrip("/") != base_url.rstrip("/"):
            raise ImportFailure(f"peer receipt belongs to a different server: {peer_receipt}")
        peer_tenant_id = str(peer.get("tenant", {}).get("id", "")).strip()
        if not peer_tenant_id:
            raise ImportFailure(f"peer receipt has no tenant ID: {peer_receipt}")
        if peer_tenant_id == tenant["id"]:
            raise ImportFailure(
                f"{scope} and peer partition use the same tenant {tenant['id']}; "
                "audit data must be imported with a different tenant API key"
            )


def nested_matches(actual: Mapping[str, Any], expected: Mapping[str, Any], prefix: str) -> List[str]:
    differences: List[str] = []
    for key, expected_value in expected.items():
        field = f"{prefix}.{key}" if prefix else key
        if key not in actual:
            differences.append(f"{field} missing")
            continue
        actual_value = actual[key]
        if isinstance(expected_value, dict):
            if not isinstance(actual_value, dict):
                differences.append(f"{field}: expected object, got {actual_value!r}")
            else:
                differences.extend(nested_matches(actual_value, expected_value, field))
        elif actual_value != expected_value:
            differences.append(f"{field}: expected {expected_value!r}, got {actual_value!r}")
    return differences


def kb_create_payload(
    spec: Mapping[str, Any],
    embedding_model_id: str,
    summary_model_id: str,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": spec["name"],
        "type": spec["type"],
        "description": spec["description"],
        "embedding_model_id": embedding_model_id,
        "summary_model_id": summary_model_id,
        "chunking_config": spec["chunking_config"],
        "indexing_strategy": {
            "vector_enabled": True,
            "keyword_enabled": True,
            "wiki_enabled": False,
            "graph_enabled": False,
        },
    }
    if spec["type"] == "faq":
        payload["faq_config"] = spec["faq_config"]
    return payload


def ensure_knowledge_bases(
    client: WeKnoraClient,
    specs: Sequence[Mapping[str, Any]],
    embedding_model_id: str,
    summary_model_id: str,
    state: Dict[str, Any],
    state_path: Path,
    adopt_existing: bool,
) -> Dict[str, Dict[str, Any]]:
    listed = flatten_page_data(
        envelope_data(client.request("GET", "/knowledge-bases"), "list knowledge bases"),
        "list knowledge bases",
    )
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for kb in listed:
        by_name.setdefault(str(kb.get("name", "")), []).append(kb)

    result: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        key = spec["key"]
        expected = kb_create_payload(spec, embedding_model_id, summary_model_id)
        matches = by_name.get(spec["name"], [])
        if len(matches) > 1:
            raise ImportFailure(f"ambiguous KB name {spec['name']!r}: {len(matches)} matches")
        state_record = state.get("knowledge_bases", {}).get(key)
        if matches:
            kb = matches[0]
            if state_record and state_record.get("id") != kb.get("id"):
                raise ImportFailure(f"state/server KB ID mismatch for {spec['name']}")
            if not state_record and not adopt_existing:
                raise ImportFailure(
                    f"KB {spec['name']!r} already exists but is not owned by this state file; "
                    "use --adopt-existing-kbs only after checking it"
                )
        else:
            if state_record:
                raise ImportFailure(f"state references missing KB {spec['name']!r}")
            created = client.request("POST", "/knowledge-bases", json_body=expected, accepted=(201,))
            kb = envelope_data(created, f"create {spec['name']}")
            if not isinstance(kb, dict) or not kb.get("id"):
                raise ImportFailure(f"create {spec['name']} returned no KB ID")
            listed.append(kb)
            by_name.setdefault(spec["name"], []).append(kb)

        differences = nested_matches(
            {
                **kb,
                # WeKnora Lite v0.7.2 serializes ChunkingConfig with
                # ``omitempty``.  A requested token_limit of 0 is therefore
                # persisted as the server default but omitted from the create
                # response and subsequent list responses.  Restore only that
                # exact zero default for comparison; all non-zero and all
                # other fields remain strict.
                "chunking_config": {
                    **(kb.get("chunking_config") or {}),
                    **(
                        {"token_limit": 0}
                        if expected["chunking_config"].get("token_limit") == 0
                        and "token_limit" not in (kb.get("chunking_config") or {})
                        else {}
                    ),
                    **(
                        {"enable_parent_child": False}
                        if expected["chunking_config"].get("enable_parent_child") is False
                        and "enable_parent_child" not in (kb.get("chunking_config") or {})
                        else {}
                    ),
                },
            },
            {
                "name": expected["name"],
                "type": expected["type"],
                "embedding_model_id": expected["embedding_model_id"],
                "summary_model_id": expected["summary_model_id"],
                "chunking_config": expected["chunking_config"],
                "indexing_strategy": expected["indexing_strategy"],
                **({"faq_config": expected["faq_config"]} if spec["type"] == "faq" else {}),
            },
            "",
        )
        if differences:
            raise ImportFailure(f"KB configuration mismatch for {spec['name']}: " + "; ".join(differences))
        result[key] = kb
        state.setdefault("knowledge_bases", {})[key] = {
            "id": kb["id"],
            "name": kb["name"],
            "type": kb["type"],
        }
        save_state(state_path, state)
    return result


def desired_tags(kb_key: str, metadata: Mapping[str, str]) -> List[str]:
    tags: List[str]
    if kb_key == "staff_courses":
        tags = ["staff-only"]
        for field in ("system", "module_id"):
            value = metadata.get(field)
            if value:
                tags.append(value)
    elif kb_key == "safety_policy":
        tags = ["safety-policy"]
    elif kb_key == "audit_raw":
        tags = ["audit-only"]
        if metadata.get("authority_level"):
            tags.append(metadata["authority_level"])
    else:
        tags = []
    return list(dict.fromkeys(tags))


def ensure_tags(
    client: WeKnoraClient,
    kb_id: str,
    names: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    page = envelope_data(
        client.request(
            "GET",
            f"/knowledge-bases/{kb_id}/tags",
            query=[("page", 1), ("page_size", 1000)],
        ),
        "list tags",
    )
    rows = flatten_page_data(page, "list tags")
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_name.setdefault(str(row.get("name", "")), []).append(row)
    result: Dict[str, Dict[str, Any]] = {}
    colors = ["#2F80ED", "#27AE60", "#9B51E0", "#F2994A", "#EB5757", "#56CCF2"]
    for index, name in enumerate(sorted(set(names))):
        matches = by_name.get(name, [])
        if len(matches) > 1:
            raise ImportFailure(f"ambiguous tag {name!r} in KB {kb_id}")
        if matches:
            tag = matches[0]
        else:
            payload = {"name": name, "color": colors[index % len(colors)], "sort_order": (index + 1) * 10}
            tag = envelope_data(
                client.request("POST", f"/knowledge-bases/{kb_id}/tags", json_body=payload),
                f"create tag {name}",
            )
            if not isinstance(tag, dict) or not tag.get("id"):
                raise ImportFailure(f"create tag {name!r} returned no UUID")
            by_name.setdefault(name, []).append(tag)
        result[name] = tag
    return result


def batch_get_documents(client: WeKnoraClient, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(ids), 50):
        batch = ids[start : start + 50]
        query = [("ids", item) for item in batch]
        payload = client.request("GET", "/knowledge/batch", query=query)
        rows = envelope_data(payload, "batch get knowledge")
        if not isinstance(rows, list):
            raise ImportFailure(f"batch get knowledge returned unexpected data: {rows!r}")
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                result[row["id"]] = row
    return result


def local_file_md5(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - WeKnora v0.7.2 defines file_hash as MD5.
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def document_metadata(value: Any, context: str) -> Mapping[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ImportFailure(f"{context}: document metadata is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ImportFailure(f"{context}: document metadata is not an object")
    return value


def verify_document_identity(
    server_row: Mapping[str, Any],
    *,
    expected_id: str,
    kb_id: str,
    relative_path: str,
    expected_file_hash: str,
    expected_metadata: Mapping[str, str],
) -> None:
    context = f"document {relative_path}"
    if str(server_row.get("id", "")) != expected_id:
        raise ImportFailure(f"{context}: remote ID mismatch")
    if str(server_row.get("knowledge_base_id", "")) != kb_id:
        raise ImportFailure(f"{context}: remote knowledge_base_id drifted")
    if str(server_row.get("file_hash", "")) != expected_file_hash:
        raise ImportFailure(f"{context}: remote file_hash differs from the snapshot bytes")
    actual_metadata = document_metadata(server_row.get("metadata"), context)
    differences = [
        key
        for key, expected in expected_metadata.items()
        if actual_metadata.get(key) != expected
    ]
    if differences:
        raise ImportFailure(
            f"{context}: remote metadata drifted for fields {sorted(differences)}"
        )


def list_all_documents(client: WeKnoraClient, kb_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page_number = 1
    while True:
        payload = client.request(
            "GET",
            f"/knowledge-bases/{kb_id}/knowledge",
            query=[("page", page_number), ("page_size", 1000)],
        )
        if (
            not isinstance(payload, dict)
            or payload.get("success") is not True
            or not isinstance(payload.get("data"), list)
        ):
            raise ImportFailure(f"list documents returned an invalid page: {payload!r}")
        page_rows = payload["data"]
        if any(not isinstance(row, dict) for row in page_rows):
            raise ImportFailure("list documents returned a non-object row")
        rows.extend(page_rows)
        try:
            total = int(payload.get("total", -1))
        except (TypeError, ValueError) as exc:
            raise ImportFailure("list documents returned no valid total") from exc
        if total < 0:
            raise ImportFailure("list documents returned no valid total")
        if len(rows) >= total:
            if len(rows) != total:
                raise ImportFailure(
                    f"list documents exceeded declared total: read={len(rows)}, total={total}"
                )
            return rows
        if not page_rows:
            raise ImportFailure(
                f"list documents stopped before total: read={len(rows)}, total={total}"
            )
        page_number += 1


def verify_document_exact_set(
    client: WeKnoraClient,
    kb_id: str,
    expected: Mapping[str, Mapping[str, Any]],
) -> None:
    remote = list_all_documents(client, kb_id)
    remote_by_id: Dict[str, Mapping[str, Any]] = {}
    for row in remote:
        document_id = str(row.get("id", ""))
        if not document_id or document_id in remote_by_id:
            raise ImportFailure(f"document KB {kb_id} returned a missing or duplicate ID")
        remote_by_id[document_id] = row
    if set(remote_by_id) != set(expected):
        raise ImportFailure(
            f"document KB {kb_id} exact-set mismatch: "
            f"missing={sorted(set(expected) - set(remote_by_id))[:5]}, "
            f"extra={sorted(set(remote_by_id) - set(expected))[:5]}"
        )
    for document_id, identity in expected.items():
        verify_document_identity(
            remote_by_id[document_id],
            expected_id=document_id,
            kb_id=kb_id,
            relative_path=str(identity["path"]),
            expected_file_hash=str(identity["file_hash"]),
            expected_metadata=identity["metadata"],
        )


def wait_for_documents(
    client: WeKnoraClient,
    records: Sequence[Dict[str, Any]],
    timeout: float,
    poll_interval: float,
) -> None:
    pending = {record["id"]: record for record in records}
    deadline = time.monotonic() + timeout
    while pending:
        if time.monotonic() >= deadline:
            remaining = ", ".join(sorted(record["path"] for record in pending.values())[:10])
            raise ImportFailure(f"document parsing timed out; remaining: {remaining}")
        server_rows = batch_get_documents(client, list(pending))
        missing = set(pending) - set(server_rows)
        if missing:
            raise ImportFailure(f"server no longer returns document IDs: {sorted(missing)}")
        for document_id, server_row in server_rows.items():
            status = str(server_row.get("parse_status", ""))
            pending[document_id]["parse_status"] = status
            if status in TERMINAL_DOCUMENT_STATES:
                record = pending.pop(document_id)
                if status != "completed":
                    raise ImportFailure(
                        f"document parse {status}: {record['path']}: "
                        f"{server_row.get('error_message', '')}"
                    )
        if pending:
            time.sleep(poll_interval)


def import_documents(
    client: WeKnoraClient,
    bundle: Path,
    specs: Sequence[Mapping[str, Any]],
    kbs: Mapping[str, Mapping[str, Any]],
    state: Dict[str, Any],
    state_path: Path,
    timeout: float,
    poll_interval: float,
) -> List[Dict[str, Any]]:
    all_records: List[Dict[str, Any]] = []
    spec_by_key = {spec["key"]: spec for spec in specs}
    for kb_key in (
        key for key in ("staff_courses", "safety_policy", "audit_raw") if key in kbs
    ):
        kb_id = str(kbs[kb_key]["id"])
        rows = read_jsonl(bundle / kb_key / "document_manifest.jsonl")
        tag_names = {
            name
            for row in rows
            for name in desired_tags(kb_key, row.get("metadata", {}))
        }
        tags = ensure_tags(client, kb_id, tag_names)
        current_records: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, 1):
            relative_path = row["path"]
            local_path = bundle / relative_path
            expected_file_hash = local_file_md5(local_path)
            metadata = dict(row.get("metadata", {}))
            metadata.update(
                {
                    "bundle_path": relative_path,
                    "bundle_sha256": row["sha256"],
                    "bundle_version": state["bundle_version"],
                }
            )
            state_record = state.setdefault("documents", {}).get(relative_path)
            if state_record:
                if state_record.get("sha256") != row["sha256"]:
                    raise ImportFailure(f"managed document changed since import: {relative_path}")
                if state_record.get("kb_id") != kb_id:
                    raise ImportFailure(f"managed document KB changed: {relative_path}")
                recorded_file_hash = str(state_record.get("file_hash", ""))
                if recorded_file_hash and recorded_file_hash != expected_file_hash:
                    raise ImportFailure(f"managed document file_hash changed: {relative_path}")
                try:
                    server_row = envelope_data(
                        client.request("GET", f"/knowledge/{state_record['id']}"),
                        f"get {relative_path}",
                    )
                    if not isinstance(server_row, dict):
                        raise ImportFailure(f"get {relative_path} returned a non-object")
                    document_id = str(state_record["id"])
                    verify_document_identity(
                        server_row,
                        expected_id=document_id,
                        kb_id=kb_id,
                        relative_path=relative_path,
                        expected_file_hash=expected_file_hash,
                        expected_metadata=metadata,
                    )
                    record = {
                        "path": relative_path,
                        "sha256": row["sha256"],
                        "id": document_id,
                        "kb_id": kb_id,
                        "file_hash": expected_file_hash,
                        "metadata": metadata,
                        "parse_status": server_row.get("parse_status", ""),
                        "reused": True,
                        "remote_identity_verified": True,
                    }
                    current_records.append(record)
                    all_records.append(record)
                    continue
                except APIError as exc:
                    if exc.status != 404:
                        raise

            document_tag_ids = [tags[name]["id"] for name in desired_tags(kb_key, metadata)]
            process_config = {"chunking_config": spec_by_key[kb_key]["chunking_config"]}
            try:
                response = client.upload_document(
                    kb_id,
                    local_path,
                    relative_path.split("/", 1)[-1],
                    metadata,
                    document_tag_ids,
                    process_config,
                )
                server_row = envelope_data(response, f"upload {relative_path}")
                reused = False
            except APIError as exc:
                duplicate = (
                    exc.status == 409
                    and isinstance(exc.payload, dict)
                    and exc.payload.get("code") == "duplicate_file"
                    and isinstance(exc.payload.get("data"), dict)
                    and exc.payload["data"].get("id")
                )
                if not duplicate:
                    raise
                server_row = exc.payload["data"]
                reused = True
            if not isinstance(server_row, dict) or not server_row.get("id"):
                raise ImportFailure(f"upload {relative_path} returned no document ID")
            document_id = str(server_row["id"])
            verify_document_identity(
                server_row,
                expected_id=document_id,
                kb_id=kb_id,
                relative_path=relative_path,
                expected_file_hash=expected_file_hash,
                expected_metadata=metadata,
            )
            record = {
                "path": relative_path,
                "sha256": row["sha256"],
                "id": document_id,
                "kb_id": kb_id,
                "file_hash": expected_file_hash,
                "metadata": metadata,
                "parse_status": server_row.get("parse_status", "pending"),
                "reused": reused,
                "remote_identity_verified": True,
            }
            state["documents"][relative_path] = dict(record)
            save_state(state_path, state)
            current_records.append(record)
            all_records.append(record)
            print(f"[{kb_key} {index}/{len(rows)}] {'reuse' if reused else 'upload'} {relative_path}")
        wait_for_documents(client, current_records, timeout, poll_interval)
        expected_remote = {
            str(record["id"]): {
                "path": record["path"],
                "file_hash": record["file_hash"],
                "metadata": record["metadata"],
            }
            for record in current_records
        }
        if len(expected_remote) != len(current_records):
            raise ImportFailure(f"document KB {kb_id} has duplicate managed document IDs")
        verify_document_exact_set(
            client,
            kb_id,
            expected_remote,
        )
        for record in current_records:
            record["kb_exact_set_verified"] = True
            state["documents"][record["path"]].update(record)
        save_state(state_path, state)
    return all_records


def wait_for_faq_task(
    client: WeKnoraClient,
    task_id: str,
    timeout: float,
    poll_interval: float,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        if time.monotonic() >= deadline:
            raise ImportFailure(f"FAQ import task timed out: {task_id}")
        payload = client.request("GET", f"/faq/import/progress/{task_id}")
        progress = envelope_data(payload, f"FAQ task {task_id}")
        if not isinstance(progress, dict):
            raise ImportFailure(f"FAQ task {task_id} returned invalid progress")
        status = str(progress.get("status", ""))
        if status in TERMINAL_FAQ_STATES:
            if status != "completed":
                raise ImportFailure(f"FAQ import failed: {progress.get('error') or progress.get('message')}")
            return progress
        time.sleep(poll_interval)


def assert_clean_faq_progress(progress: Mapping[str, Any], expected_total: int, label: str) -> None:
    if int(progress.get("total", -1)) != expected_total:
        raise ImportFailure(f"{label}: expected total {expected_total}, got {progress.get('total')}")
    if int(progress.get("processed", -1)) != expected_total:
        raise ImportFailure(f"{label}: processed count mismatch: {progress.get('processed')}")
    if int(progress.get("failed_count", 0)) != 0:
        raise ImportFailure(f"{label}: failed entries: {progress.get('failed_entries')}")
    if int(progress.get("partial_failed_count", 0)) != 0:
        raise ImportFailure(f"{label}: partial failures: {progress.get('failed_entries')}")


def list_all_faq_entries(client: WeKnoraClient, kb_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page_number = 1
    while True:
        page = envelope_data(
            client.request(
                "GET",
                f"/knowledge-bases/{kb_id}/faq/entries",
                query=[("page", page_number), ("page_size", 1000)],
            ),
            "list FAQ entries",
        )
        if not isinstance(page, dict) or not isinstance(page.get("data"), list):
            raise ImportFailure(f"list FAQ entries returned an invalid page: {page!r}")
        page_rows = page["data"]
        if any(not isinstance(row, dict) for row in page_rows):
            raise ImportFailure("list FAQ entries returned a non-object row")
        rows.extend(page_rows)
        total = int(page.get("total", -1))
        if total < 0:
            raise ImportFailure("list FAQ entries returned no valid total")
        if len(rows) >= total:
            if len(rows) != total:
                raise ImportFailure(
                    f"list FAQ entries exceeded declared total: read={len(rows)}, total={total}"
                )
            return rows
        if not page_rows:
            raise ImportFailure(
                f"list FAQ entries stopped before total: read={len(rows)}, total={total}"
            )
        page_number += 1


def assert_faq_entry_identity(
    rows: Sequence[Mapping[str, Any]],
    kb_id: str,
    label: str,
) -> None:
    numeric_ids: List[str] = []
    chunk_ids: List[str] = []
    for row in rows:
        if str(row.get("knowledge_base_id", "")) != kb_id:
            raise ImportFailure(
                f"{label}: FAQ row belongs to unexpected KB: {row.get('knowledge_base_id')!r}"
            )
        numeric_id = str(row.get("id", "")).strip()
        chunk_id = str(row.get("chunk_id", "")).strip()
        if not numeric_id or not chunk_id:
            raise ImportFailure(f"{label}: FAQ row is missing id or chunk_id")
        numeric_ids.append(numeric_id)
        chunk_ids.append(chunk_id)
    if len(set(numeric_ids)) != len(numeric_ids):
        raise ImportFailure(f"{label}: duplicate numeric FAQ IDs")
    if len(set(chunk_ids)) != len(chunk_ids):
        raise ImportFailure(f"{label}: duplicate FAQ chunk IDs")


def faq_canonical(entry: Mapping[str, Any]) -> Dict[str, Any]:
    def string_list(field: str) -> List[str]:
        value = entry.get(field)
        # Lite v0.7.2 returns SQL NULL for an empty FAQ string-array.  Treat
        # only NULL as the empty list; reject every other non-list shape so a
        # malformed remote entry cannot pass the exact-set comparison.
        if value is None:
            return []
        if not isinstance(value, list):
            raise ImportFailure(f"FAQ field {field} must be a list or null")
        return [str(item).strip() for item in value]

    return {
        "standard_question": str(entry.get("standard_question", "")).strip(),
        "similar_questions": sorted(string_list("similar_questions")),
        "negative_questions": sorted(string_list("negative_questions")),
        "answers": string_list("answers"),
        "answer_strategy": entry.get("answer_strategy"),
        "tag_name": entry.get("tag_name"),
        "is_enabled": bool(entry.get("is_enabled")),
        "is_recommended": bool(entry.get("is_recommended")),
    }


def import_faq_set(
    client: WeKnoraClient,
    bundle: Path,
    bundle_key: str,
    kb_id: str,
    state: Dict[str, Any],
    state_path: Path,
    timeout: float,
    poll_interval: float,
    allow_replace_existing: bool,
) -> Dict[str, Any]:
    entries = read_json(bundle / bundle_key / "faq_entries.json")
    existing = list_all_faq_entries(client, kb_id)
    managed_record = state.get("faq_imports", {}).get(bundle_key, {})
    managed_before = (
        managed_record.get("kb_id") == kb_id
        and managed_record.get("flags_patched_and_verified") is True
    )
    if existing and not managed_before and not allow_replace_existing:
        raise ImportFailure(
            f"FAQ KB {bundle_key} already has {len(existing)} entries; replace would delete unmatched data. "
            "Use --replace-existing-faq only after confirming the scope."
        )

    task_results: Dict[str, Any] = {}
    for dry_run in (True, False):
        phase = "dry_run" if dry_run else "import"
        payload = {"mode": "replace", "dry_run": dry_run, "entries": entries}
        response = client.request(
            "POST",
            f"/knowledge-bases/{kb_id}/faq/entries",
            json_body=payload,
        )
        data = envelope_data(response, f"start FAQ {phase}")
        if not isinstance(data, dict) or not data.get("task_id"):
            raise ImportFailure(f"FAQ {phase} returned no task ID")
        task_id = str(data["task_id"])
        progress = wait_for_faq_task(client, task_id, timeout, poll_interval)
        assert_clean_faq_progress(progress, len(entries), f"{bundle_key} {phase}")
        task_results[phase] = {"task_id": task_id, "progress": progress}
        state.setdefault("faq_attempts", {}).setdefault(bundle_key, {})[phase] = task_results[phase]
        save_state(state_path, state)

    actual = list_all_faq_entries(client, kb_id)
    assert_faq_entry_identity(actual, kb_id, f"{bundle_key} post-import")
    expected_by_question = {row["standard_question"].strip(): row for row in entries}
    actual_by_question: Dict[str, List[Dict[str, Any]]] = {}
    for row in actual:
        actual_by_question.setdefault(str(row.get("standard_question", "")).strip(), []).append(row)
    if set(actual_by_question) != set(expected_by_question):
        raise ImportFailure(
            f"{bundle_key} FAQ standard-question set mismatch after import: "
            f"missing={sorted(set(expected_by_question) - set(actual_by_question))[:5]}, "
            f"extra={sorted(set(actual_by_question) - set(expected_by_question))[:5]}"
        )
    if any(len(rows) != 1 for rows in actual_by_question.values()):
        raise ImportFailure(f"{bundle_key} has duplicate standard questions after import")

    by_id: Dict[str, Dict[str, bool]] = {}
    for question, expected in expected_by_question.items():
        actual_row = actual_by_question[question][0]
        by_id[str(actual_row["id"])] = {
            "is_enabled": bool(expected["is_enabled"]),
            "is_recommended": bool(expected["is_recommended"]),
        }
    envelope_data(
        client.request(
            "PUT",
            f"/knowledge-bases/{kb_id}/faq/entries/fields",
            json_body={"by_id": by_id, "exclude_ids": []},
        ),
        f"patch FAQ flags for {bundle_key}",
    )

    reread = list_all_faq_entries(client, kb_id)
    assert_faq_entry_identity(reread, kb_id, f"{bundle_key} post-patch")
    reread_by_question = {str(row["standard_question"]).strip(): row for row in reread}
    if len(reread_by_question) != len(entries):
        raise ImportFailure(f"{bundle_key} FAQ count mismatch after flag patch")
    for question, expected in expected_by_question.items():
        actual_row = reread_by_question.get(question)
        if actual_row is None:
            raise ImportFailure(f"{bundle_key} FAQ missing after patch: {question}")
        expected_canonical = faq_canonical(expected)
        actual_canonical = faq_canonical(actual_row)
        if actual_canonical != expected_canonical:
            raise ImportFailure(
                f"{bundle_key} FAQ mismatch after patch for {question!r}: "
                f"expected={expected_canonical!r}, actual={actual_canonical!r}"
            )

    result = {
        "kb_id": kb_id,
        "entry_count": len(entries),
        "dry_run": task_results["dry_run"],
        "import": task_results["import"],
        "flags_patched_and_verified": True,
    }
    state["faq_imports"][bundle_key] = result
    state.get("faq_attempts", {}).pop(bundle_key, None)
    save_state(state_path, state)
    return result


def run_retrieval_smoke_tests(
    client: WeKnoraClient,
    bundle: Path,
    kbs: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    tests = [
        {
            "name": "staff-course",
            "query": "秀域品牌的业务板块有哪些？",
            "kb_keys": ["staff_courses"],
            "expect_results": True,
        },
        {
            "name": "customer-provisional-disabled",
            "query": read_json(bundle / "customer_approved" / "faq_entries.json")[0]["standard_question"],
            "kb_keys": ["customer_approved"],
            "expect_results": False,
        },
        {
            "name": "safety-policy",
            "query": "服务中胸闷头晕应如何处理？",
            "kb_keys": ["safety_policy"],
            "expect_results": True,
        },
        {
            "name": "safety-boundary-provisional-disabled",
            "query": read_json(bundle / "safety_boundary" / "faq_entries.json")[0]["standard_question"],
            "kb_keys": ["safety_boundary"],
            "expect_results": False,
        },
    ]
    results: List[Dict[str, Any]] = []
    for test in tests:
        kb_ids = [str(kbs[key]["id"]) for key in test["kb_keys"]]
        response = client.request(
            "POST",
            "/knowledge-search",
            json_body={"query": test["query"], "knowledge_base_ids": kb_ids},
        )
        rows = envelope_data(response, f"retrieval smoke test {test['name']}")
        if not isinstance(rows, list):
            raise ImportFailure(f"retrieval smoke test returned a non-list: {test['name']}")
        if test["expect_results"] and not rows:
            raise ImportFailure(f"retrieval smoke test returned no results: {test['name']}")
        if not test["expect_results"] and rows:
            raise ImportFailure(
                "disabled provisional FAQ leaked into retrieval: "
                f"{test['name']} returned {len(rows)} result(s)"
            )
        unexpected_sources = []
        for row in rows:
            if not isinstance(row, dict):
                unexpected_sources.append("<non-object>")
                continue
            source = str(row.get("knowledge_base_id", "")).strip()
            if not source or source not in kb_ids:
                unexpected_sources.append(source or "<missing>")
        unexpected_sources = sorted(set(unexpected_sources))
        if unexpected_sources:
            raise ImportFailure(
                f"retrieval smoke test escaped requested KB scope: {test['name']}: "
                f"{unexpected_sources}"
            )
        results.append(
            {
                "name": test["name"],
                "query": test["query"],
                "knowledge_base_ids": kb_ids,
                "expected": "non_empty" if test["expect_results"] else "empty",
                "result_count": len(rows),
            }
        )
    return results


def build_plan(bundle: Path, validation: Mapping[str, Any], scope: str) -> Dict[str, Any]:
    manifest = read_json(bundle / "bundle_manifest.json")
    selected = [
        row for row in manifest["knowledge_bases"] if row.get("tenant_group") == scope
    ]
    selected_keys = {row["key"] for row in selected}
    return {
        "mode": "plan",
        "tenant_partition": scope,
        "bundle": str(bundle.resolve()),
        "bundle_validation": validation["status"],
        "weknora_pin": manifest["weknora"],
        "knowledge_bases": [
            {
                "key": row["key"],
                "name": row["name"],
                "type": row["type"],
                "access_policy": row["access_policy"],
            }
            for row in selected
        ],
        "documents": {
            key: count
            for key, count in {
                "staff_courses": manifest["counts"]["staff_documents"],
                "safety_policy": manifest["counts"]["safety_documents"],
                "audit_raw": manifest["counts"]["audit_documents"],
            }.items()
            if key in selected_keys
        },
        "faq_entries": {
            key: count
            for key, count in {
                "customer_approved": manifest["counts"]["customer_faq_payload_entries"],
                "safety_boundary": manifest["counts"]["safety_boundary_faq_entries"],
            }.items()
            if key in selected_keys
        },
        "next_command": (
            "use the API key for this tenant partition, set the model IDs, "
            f"then rerun with --scope {scope} --apply"
        ),
    }


def _apply_import_from_snapshot(
    args: argparse.Namespace,
    validation: Mapping[str, Any],
) -> Dict[str, Any]:
    api_key = args.api_key or os.environ.get("WEKNORA_API_KEY", "")
    embedding_model_id = args.embedding_model_id or os.environ.get("WEKNORA_EMBEDDING_MODEL_ID", "")
    summary_model_id = args.summary_model_id or os.environ.get("WEKNORA_SUMMARY_MODEL_ID", "")
    missing = [
        name
        for name, value in [
            ("WEKNORA_API_KEY", api_key),
            ("WEKNORA_EMBEDDING_MODEL_ID", embedding_model_id),
            ("WEKNORA_SUMMARY_MODEL_ID", summary_model_id),
        ]
        if not value
    ]
    if missing:
        raise ImportFailure("missing required secret/config environment variables: " + ", ".join(missing))

    bundle = args.bundle.resolve()
    manifest = read_json(bundle / "bundle_manifest.json")
    client = WeKnoraClient(args.base_url, api_key, timeout=args.http_timeout)
    server = ensure_server_version(client, args.allow_version_mismatch)
    tenant = get_current_tenant(client)
    verify_tenant_partition(
        tenant,
        args.scope,
        args.expected_tenant_id,
        args.peer_receipt,
        manifest["bundle_version"],
        validation["bundle_manifest_sha256"],
        client.base_url,
    )
    state = load_state(
        args.state,
        manifest["bundle_version"],
        validation["bundle_manifest_sha256"],
        args.base_url,
        args.scope,
        tenant["id"],
    )
    specs = [
        spec
        for spec in manifest["knowledge_bases"]
        if spec.get("tenant_group") == args.scope
    ]
    if not specs:
        raise ImportFailure(f"bundle has no KBs for tenant partition {args.scope!r}")
    kbs = ensure_knowledge_bases(
        client,
        specs,
        embedding_model_id,
        summary_model_id,
        state,
        args.state,
        args.adopt_existing_kbs,
    )
    documents = import_documents(
        client,
        bundle,
        specs,
        kbs,
        state,
        args.state,
        args.wait_timeout,
        args.poll_interval,
    )
    faq_results: Dict[str, Any] = {}
    if args.scope == "runtime":
        faq_results = {
            "customer_approved": import_faq_set(
                client,
                bundle,
                "customer_approved",
                str(kbs["customer_approved"]["id"]),
                state,
                args.state,
                args.wait_timeout,
                args.poll_interval,
                args.replace_existing_faq,
            ),
            "safety_boundary": import_faq_set(
                client,
                bundle,
                "safety_boundary",
                str(kbs["safety_boundary"]["id"]),
                state,
                args.state,
                args.wait_timeout,
                args.poll_interval,
                args.replace_existing_faq,
            ),
        }
        smoke_tests = run_retrieval_smoke_tests(client, bundle, kbs)
    else:
        response = client.request(
            "POST",
            "/knowledge-search",
            json_body={
                "query": "迁移治理记录",
                "knowledge_base_ids": [str(kbs["audit_raw"]["id"])],
            },
        )
        rows = envelope_data(response, "audit retrieval smoke test")
        if not isinstance(rows, list) or not rows:
            raise ImportFailure("audit retrieval smoke test returned no results")
        audit_id = str(kbs["audit_raw"]["id"])
        if any(
            not isinstance(row, dict)
            or str(row.get("knowledge_base_id", "")) != audit_id
            for row in rows
        ):
            raise ImportFailure("audit retrieval smoke test escaped the audit KB")
        smoke_tests = [
            {
                "name": "audit-governance",
                "query": "迁移治理记录",
                "knowledge_base_ids": [audit_id],
                "expected": "non_empty",
                "result_count": len(rows),
            }
        ]
    receipt = {
        "status": "passed",
        "completed_at": utc_now(),
        "base_url": client.base_url,
        "bundle_version": manifest["bundle_version"],
        "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
        "tenant_partition": args.scope,
        "tenant": tenant,
        "bundle_validation_checks": validation["checks"],
        "weknora_expected": manifest["weknora"],
        "server": server,
        "models": {
            "embedding_model_id": embedding_model_id,
            "summary_model_id": summary_model_id,
        },
        "knowledge_bases": {
            key: {
                "id": row["id"],
                "name": row["name"],
                "type": row["type"],
                "access_policy": next(spec["access_policy"] for spec in specs if spec["key"] == key),
            }
            for key, row in kbs.items()
        },
        "documents": documents,
        "faq_imports": faq_results,
        "retrieval_smoke_tests": smoke_tests,
        "agent_binding_policy": (
            {
                "staff_initial": ["staff_courses", "safety_policy"],
                "staff_after_boundary_approval": ["staff_courses", "safety_policy", "safety_boundary"],
                "customer_after_business_approval": ["customer_approved"],
                "customer_after_all_faq_approval": ["customer_approved", "safety_boundary"],
                "customer_policy_note": "safety_policy remains staff-only until a named policy review is recorded",
                "never_bind": ["audit_raw"],
            }
            if args.scope == "runtime"
            else {"never_bind_to_runtime_agents": ["audit_raw"]}
        ),
    }
    write_json_atomic(args.receipt, receipt)
    state["completed_at"] = receipt["completed_at"]
    state["receipt"] = str(args.receipt.resolve())
    save_state(args.state, state)
    return receipt


def apply_import(
    args: argparse.Namespace,
    expected_validation: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate and import one private, read-only copy of the source bundle."""

    source = args.bundle.resolve()
    snapshot_args = argparse.Namespace(**vars(args))
    snapshot_args.state = args.state.resolve()
    snapshot_args.receipt = args.receipt.resolve()
    snapshot_args.peer_receipt = args.peer_receipt.resolve()
    output_paths = (
        ("state", snapshot_args.state),
        ("receipt", snapshot_args.receipt),
        ("peer receipt", snapshot_args.peer_receipt),
    )
    if len({path for _, path in output_paths}) != len(output_paths):
        raise ImportFailure("state, receipt, and peer receipt paths must be distinct")
    for label, path in output_paths:
        try:
            path.relative_to(source)
        except ValueError:
            continue
        raise ImportFailure(f"{label} path must not be inside the source bundle: {path}")

    with immutable_bundle_snapshot(source) as snapshot:
        snapshot_validation = validate_bundle(snapshot, rebuild_check=False)
        if expected_validation is not None:
            for field in ("bundle_version", "bundle_manifest_sha256"):
                if expected_validation.get(field) != snapshot_validation.get(field):
                    raise ImportFailure(
                        f"source bundle changed after caller validation: {field}"
                    )
        snapshot_args.bundle = snapshot
        return _apply_import_from_snapshot(snapshot_args, snapshot_validation)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--base-url", default=os.environ.get("WEKNORA_URL", "http://127.0.0.1:18081"))
    parser.add_argument(
        "--scope",
        choices=("runtime", "audit"),
        default="runtime",
        help="runtime and audit must use API keys from different tenants",
    )
    parser.add_argument("--state", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--peer-receipt", type=Path)
    parser.add_argument(
        "--expected-tenant-id",
        default=os.environ.get("WEKNORA_EXPECTED_TENANT_ID", ""),
    )
    parser.add_argument("--api-key", default="", help="prefer WEKNORA_API_KEY to avoid shell history")
    parser.add_argument("--embedding-model-id", default="", help="or WEKNORA_EMBEDDING_MODEL_ID")
    parser.add_argument("--summary-model-id", default="", help="or WEKNORA_SUMMARY_MODEL_ID")
    parser.add_argument("--apply", action="store_true", help="perform the remote import")
    parser.add_argument("--adopt-existing-kbs", action="store_true")
    parser.add_argument("--replace-existing-faq", action="store_true")
    parser.add_argument("--allow-version-mismatch", action="store_true")
    parser.add_argument("--wait-timeout", type=float, default=7200.0)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--http-timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.scope == "runtime":
        args.state = args.state or DEFAULT_STATE_RUNTIME
        args.receipt = args.receipt or DEFAULT_RECEIPT_RUNTIME
        args.peer_receipt = args.peer_receipt or DEFAULT_RECEIPT_AUDIT
    else:
        args.state = args.state or DEFAULT_STATE_AUDIT
        args.receipt = args.receipt or DEFAULT_RECEIPT_AUDIT
        args.peer_receipt = args.peer_receipt or DEFAULT_RECEIPT_RUNTIME

    try:
        if not args.apply:
            validation = validate_bundle(args.bundle, rebuild_check=False)
            print(json.dumps(build_plan(args.bundle, validation, args.scope), ensure_ascii=False, indent=2))
            return 0
        receipt = apply_import(args)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    except (ImportFailure, BundleValidationError, FileNotFoundError, KeyError, OSError, ValueError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
