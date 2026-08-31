#!/usr/bin/env python3
"""Safely replace the single Runtime safety-policy document in WeKnora Lite.

This is deliberately a delta upgrader, not a general bundle importer.  It is
intended for the v5 -> v6 migration where every Runtime payload except the one
``safety_policy`` document is unchanged.  The command:

* imports only immutable snapshots of the old and new bundles;
* binds the operation to the v5 Runtime receipt, state, server, and tenant;
* proves the safety KB is the exact one-document v5 set before mutation;
* uploads and parses v6 before asynchronously deleting v5;
* proves the final KB exact-set and retrieval identity; and
* makes a best-effort, upload-first rollback to v5 on every failure.

The caller provisions and revokes the temporary API key.  Its plaintext is
accepted only through ``WEKNORA_API_KEY`` and is never written or printed.
``EXPECTED_TENANT`` must contain the Runtime tenant ID.
"""

from __future__ import annotations

import argparse
import difflib
import fcntl
import hashlib
import json
import os
import re
import stat
import sys
import time
import urllib.parse
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence

from import_bundle import (
    APIError,
    EXPECTED_COMMIT,
    EXPECTED_VERSION,
    ImportFailure,
    WeKnoraClient,
    document_metadata,
    envelope_data,
    flatten_page_data,
    immutable_bundle_snapshot,
    kb_create_payload,
    list_all_documents,
    local_file_md5,
    nested_matches,
    verify_document_exact_set,
    verify_document_identity,
    wait_for_documents,
)


DEFAULT_BASE_URL = "http://127.0.0.1:8080"
SAFETY_KEY = "safety_policy"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json_object(path: Path, label: str) -> Dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ImportFailure(f"{label} must be a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportFailure(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ImportFailure(f"{label} must contain a JSON object: {path}")
    return value


def read_single_jsonl_object(path: Path, label: str) -> Dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ImportFailure(f"{label} must be a regular file: {path}")
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ImportFailure(f"{label} contains invalid JSON on line {line_number}") from exc
        if not isinstance(value, dict):
            raise ImportFailure(f"{label} line {line_number} is not an object")
        rows.append(value)
    if len(rows) != 1:
        raise ImportFailure(f"{label} must contain exactly one document, found {len(rows)}")
    return rows[0]


def normalize_loopback_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ImportFailure("invalid WeKnora base URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ImportFailure("WeKnora base URL must use http or https")
    if parsed.username or parsed.password:
        raise ImportFailure("WeKnora base URL must not contain credentials")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise ImportFailure("safety delta sync must use a loopback WeKnora URL")
    if parsed.query or parsed.fragment or parsed.path.rstrip("/") not in {"", "/api/v1"}:
        raise ImportFailure("WeKnora base URL must be an origin or end in /api/v1")
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    authority = host + (f":{port}" if port is not None else "")
    return f"{parsed.scheme}://{authority}"


@dataclass(frozen=True)
class SafetyBundle:
    root: Path
    version: str
    manifest_sha256: str
    weknora: Mapping[str, Any]
    kb_spec: Mapping[str, Any]
    row: Mapping[str, Any]
    relative_path: str
    file_path: Path
    file_sha256: str
    file_md5: str
    size_bytes: int
    base_metadata: Mapping[str, str]

    @property
    def remote_metadata(self) -> Dict[str, str]:
        result = dict(self.base_metadata)
        result.update(
            {
                "bundle_path": self.relative_path,
                "bundle_sha256": self.file_sha256,
                "bundle_version": self.version,
            }
        )
        return result


@dataclass(frozen=True)
class ControlFiles:
    tenant: Mapping[str, str]
    kb_id: str
    old_document_id: str
    embedding_model_id: str
    summary_model_id: str
    receipt_sha256: str
    state_sha256: str
    receipt_path: Path
    state_path: Path


@dataclass
class MutationJournal:
    started_at: str = field(default_factory=utc_now)
    phase: str = "initializing"
    mutation_started: bool = False
    new_document_id: str = ""
    old_delete_attempted: bool = False
    old_delete_may_be_inflight: bool = False
    old_delete_task_id: str = ""
    rollback: Dict[str, Any] = field(
        default_factory=lambda: {"attempted": False, "status": "not_needed"}
    )
    retrieval_checks: List[Dict[str, Any]] = field(default_factory=list)


def load_safety_bundle(root: Path, label: str) -> SafetyBundle:
    manifest_path = root / "bundle_manifest.json"
    manifest = read_json_object(manifest_path, f"{label} bundle manifest")
    version = str(manifest.get("bundle_version", "")).strip()
    if not version:
        raise ImportFailure(f"{label} bundle has no bundle_version")
    weknora = manifest.get("weknora")
    if not isinstance(weknora, dict):
        raise ImportFailure(f"{label} bundle has no WeKnora pin")
    if str(weknora.get("version", "")).lstrip("v") != EXPECTED_VERSION.lstrip("v"):
        raise ImportFailure(f"{label} bundle is not pinned to {EXPECTED_VERSION}")
    if str(weknora.get("commit", "")) != EXPECTED_COMMIT:
        raise ImportFailure(f"{label} bundle has an unexpected WeKnora commit")

    knowledge_bases = manifest.get("knowledge_bases")
    if not isinstance(knowledge_bases, list):
        raise ImportFailure(f"{label} bundle has no knowledge-base list")
    matches = [
        row
        for row in knowledge_bases
        if isinstance(row, dict)
        and row.get("key") == SAFETY_KEY
        and row.get("tenant_group") == "runtime"
    ]
    if len(matches) != 1:
        raise ImportFailure(f"{label} bundle must define one Runtime safety_policy KB")
    kb_spec = matches[0]
    if kb_spec.get("type") != "document":
        raise ImportFailure(f"{label} safety_policy KB is not a document KB")

    row = read_single_jsonl_object(
        root / SAFETY_KEY / "document_manifest.jsonl",
        f"{label} safety document manifest",
    )
    relative_path = str(row.get("path", "")).strip()
    pure_path = PurePosixPath(relative_path)
    if (
        not relative_path
        or pure_path.is_absolute()
        or ".." in pure_path.parts
        or not pure_path.parts
        or pure_path.parts[0] != SAFETY_KEY
    ):
        raise ImportFailure(f"{label} safety document has an unsafe path")
    file_path = root.joinpath(*pure_path.parts)
    if not file_path.is_file() or file_path.is_symlink():
        raise ImportFailure(f"{label} safety document is not a regular file")
    try:
        file_path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ImportFailure(f"{label} safety document escapes the bundle") from exc

    file_sha256 = sha256_file(file_path)
    size_bytes = file_path.stat().st_size
    if str(row.get("sha256", "")) != file_sha256:
        raise ImportFailure(f"{label} safety document SHA-256 does not match its manifest")
    if int(row.get("size_bytes", -1)) != size_bytes:
        raise ImportFailure(f"{label} safety document size does not match its manifest")
    metadata = row.get("metadata")
    if not isinstance(metadata, dict) or not str(metadata.get("document_id", "")).strip():
        raise ImportFailure(f"{label} safety document metadata has no stable document_id")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()):
        raise ImportFailure(f"{label} safety document metadata must contain string fields")
    counts = manifest.get("counts")
    if isinstance(counts, dict) and int(counts.get("safety_documents", -1)) != 1:
        raise ImportFailure(f"{label} bundle safety document count is not one")

    return SafetyBundle(
        root=root,
        version=version,
        manifest_sha256=sha256_file(manifest_path),
        weknora=weknora,
        kb_spec=kb_spec,
        row=row,
        relative_path=relative_path,
        file_path=file_path,
        file_sha256=file_sha256,
        file_md5=local_file_md5(file_path),
        size_bytes=size_bytes,
        base_metadata=dict(metadata),
    )


def validate_delta_shape(old: SafetyBundle, new: SafetyBundle) -> None:
    if old.version == new.version:
        raise ImportFailure("old and new bundles have the same version")
    if dict(old.kb_spec) != dict(new.kb_spec):
        raise ImportFailure("the Runtime safety KB configuration changed; delta sync is unsafe")
    for field_name, old_value, new_value in (
        ("path", old.relative_path, new.relative_path),
        ("title", old.row.get("title"), new.row.get("title")),
        ("metadata", dict(old.base_metadata), dict(new.base_metadata)),
    ):
        if old_value != new_value:
            raise ImportFailure(f"safety document {field_name} changed outside its content")
    if old.file_sha256 == new.file_sha256 or old.file_md5 == new.file_md5:
        raise ImportFailure("the new safety document bytes are identical to the old document")


def _receipt_document(receipt: Mapping[str, Any], relative_path: str) -> Mapping[str, Any]:
    rows = receipt.get("documents")
    if not isinstance(rows, list):
        raise ImportFailure("Runtime receipt has no document records")
    matches = [row for row in rows if isinstance(row, dict) and row.get("path") == relative_path]
    if len(matches) != 1:
        raise ImportFailure("Runtime receipt does not contain exactly one safety document record")
    return matches[0]


def validate_control_files(
    receipt_path: Path,
    state_path: Path,
    old: SafetyBundle,
    base_url: str,
    expected_tenant: str,
) -> ControlFiles:
    receipt = read_json_object(receipt_path, "Runtime receipt")
    state = read_json_object(state_path, "Runtime import state")
    checks = (
        (receipt.get("status") == "passed", "Runtime receipt is not passed"),
        (receipt.get("tenant_partition") == "runtime", "receipt is not the Runtime partition"),
        (state.get("tenant_partition") == "runtime", "state is not the Runtime partition"),
        (receipt.get("bundle_version") == old.version, "receipt is not for the old bundle"),
        (state.get("bundle_version") == old.version, "state is not for the old bundle"),
        (
            receipt.get("bundle_manifest_sha256") == old.manifest_sha256,
            "receipt old-bundle manifest hash differs",
        ),
        (
            state.get("bundle_manifest_sha256") == old.manifest_sha256,
            "state old-bundle manifest hash differs",
        ),
        (
            str(receipt.get("base_url", "")).rstrip("/") == base_url,
            "receipt belongs to another WeKnora server",
        ),
        (
            str(state.get("base_url", "")).rstrip("/") == base_url,
            "state belongs to another WeKnora server",
        ),
    )
    for passed, message in checks:
        if not passed:
            raise ImportFailure(message)

    receipt_tenant = receipt.get("tenant")
    if not isinstance(receipt_tenant, dict):
        raise ImportFailure("Runtime receipt has no tenant")
    tenant_id = str(receipt_tenant.get("id", "")).strip()
    tenant_name = str(receipt_tenant.get("name", "")).strip()
    if tenant_id != expected_tenant or not tenant_name:
        raise ImportFailure("Runtime receipt tenant differs from EXPECTED_TENANT")
    if str(state.get("tenant_id", "")) != tenant_id:
        raise ImportFailure("Runtime state tenant differs from the receipt")

    receipt_kbs = receipt.get("knowledge_bases")
    state_kbs = state.get("knowledge_bases")
    if not isinstance(receipt_kbs, dict) or not isinstance(state_kbs, dict):
        raise ImportFailure("Runtime control files have no knowledge-base map")
    receipt_kb = receipt_kbs.get(SAFETY_KEY)
    state_kb = state_kbs.get(SAFETY_KEY)
    if not isinstance(receipt_kb, dict) or not isinstance(state_kb, dict):
        raise ImportFailure("Runtime control files have no safety_policy KB")
    kb_id = str(receipt_kb.get("id", "")).strip()
    if not kb_id or str(state_kb.get("id", "")) != kb_id:
        raise ImportFailure("Runtime receipt/state safety KB IDs differ")
    if receipt_kb.get("name") != old.kb_spec.get("name"):
        raise ImportFailure("Runtime receipt safety KB name differs from the bundle")

    state_documents = state.get("documents")
    if not isinstance(state_documents, dict):
        raise ImportFailure("Runtime state has no document map")
    state_document = state_documents.get(old.relative_path)
    if not isinstance(state_document, dict):
        raise ImportFailure("Runtime state has no safety document record")
    receipt_document = _receipt_document(receipt, old.relative_path)
    old_document_id = str(state_document.get("id", "")).strip()
    if not old_document_id or str(receipt_document.get("id", "")) != old_document_id:
        raise ImportFailure("Runtime receipt/state safety document IDs differ")
    for label, row in (("receipt", receipt_document), ("state", state_document)):
        if row.get("kb_id") != kb_id:
            raise ImportFailure(f"Runtime {label} safety document KB differs")
        if row.get("sha256") != old.file_sha256:
            raise ImportFailure(f"Runtime {label} safety document SHA-256 differs")
        if str(row.get("file_hash", "")) != old.file_md5:
            raise ImportFailure(f"Runtime {label} safety document MD5 differs")

    models = receipt.get("models")
    if not isinstance(models, dict):
        raise ImportFailure("Runtime receipt has no model IDs")
    embedding_model_id = str(models.get("embedding_model_id", "")).strip()
    summary_model_id = str(models.get("summary_model_id", "")).strip()
    if not embedding_model_id or not summary_model_id:
        raise ImportFailure("Runtime receipt model IDs are incomplete")
    return ControlFiles(
        tenant={"id": tenant_id, "name": tenant_name},
        kb_id=kb_id,
        old_document_id=old_document_id,
        embedding_model_id=embedding_model_id,
        summary_model_id=summary_model_id,
        receipt_sha256=sha256_file(receipt_path),
        state_sha256=sha256_file(state_path),
        receipt_path=receipt_path,
        state_path=state_path,
    )


def verify_v072_legacy_server(client: WeKnoraClient) -> Dict[str, Any]:
    health = client.request("GET", "/health", api=False, accepted=(200,))
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise ImportFailure("WeKnora health endpoint returned an unexpected payload")
    payload = client.request("GET", "/system/info", accepted=(200,))
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise ImportFailure("WeKnora system info is not the v0.7.2 legacy envelope")
    info = payload.get("data")
    if not isinstance(info, dict):
        raise ImportFailure("WeKnora system info has no data object")
    version = str(info.get("version", "")).strip()
    commit = str(info.get("commit_id", "")).strip()
    edition = str(info.get("edition", "")).strip().lower()
    if version.lstrip("v") != EXPECTED_VERSION.lstrip("v"):
        raise ImportFailure(f"WeKnora server is not {EXPECTED_VERSION}")
    if not commit or not (EXPECTED_COMMIT.startswith(commit) or commit.startswith(EXPECTED_COMMIT)):
        raise ImportFailure("WeKnora server commit differs from the pinned v0.7.2 build")
    if edition != "lite":
        raise ImportFailure("WeKnora server is not the Lite edition")
    return {"version": version, "commit_id": commit, "edition": edition}


def verify_remote_tenant(client: WeKnoraClient, expected: Mapping[str, str]) -> None:
    data = envelope_data(client.request("GET", "/auth/me"), "current tenant")
    if not isinstance(data, dict) or not isinstance(data.get("tenant"), dict):
        raise ImportFailure("current tenant response has an invalid envelope")
    tenant = data["tenant"]
    if str(tenant.get("id", "")) != expected["id"] or str(tenant.get("name", "")) != expected["name"]:
        raise ImportFailure("API key authenticates into a different Runtime tenant")


def _normalized_remote_kb(row: Mapping[str, Any], expected: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    actual_chunking = dict(row.get("chunking_config") or {})
    expected_chunking = dict(expected.get("chunking_config") or {})
    if expected_chunking.get("token_limit") == 0 and "token_limit" not in actual_chunking:
        actual_chunking["token_limit"] = 0
    if (
        expected_chunking.get("enable_parent_child") is False
        and "enable_parent_child" not in actual_chunking
    ):
        actual_chunking["enable_parent_child"] = False
    result["chunking_config"] = actual_chunking
    return result


def verify_remote_kb(
    client: WeKnoraClient,
    bundle: SafetyBundle,
    controls: ControlFiles,
) -> Mapping[str, Any]:
    listed = flatten_page_data(
        envelope_data(client.request("GET", "/knowledge-bases"), "list knowledge bases"),
        "list knowledge bases",
    )
    matches = [row for row in listed if str(row.get("name", "")) == bundle.kb_spec["name"]]
    if len(matches) != 1:
        raise ImportFailure("remote Runtime has an ambiguous or missing safety KB")
    row = matches[0]
    if str(row.get("id", "")) != controls.kb_id:
        raise ImportFailure("remote safety KB ID differs from the Runtime receipt")
    expected = kb_create_payload(
        bundle.kb_spec,
        controls.embedding_model_id,
        controls.summary_model_id,
    )
    differences = nested_matches(_normalized_remote_kb(row, expected), expected, "safety_policy")
    if differences:
        raise ImportFailure("remote safety KB configuration drifted: " + "; ".join(differences[:5]))
    return row


def existing_safety_tag_id(client: WeKnoraClient, kb_id: str) -> str:
    page = envelope_data(
        client.request(
            "GET",
            f"/knowledge-bases/{kb_id}/tags",
            query=[("page", 1), ("page_size", 1000)],
        ),
        "list safety tags",
    )
    rows = flatten_page_data(page, "list safety tags")
    matches = [row for row in rows if str(row.get("name", "")) == "safety-policy"]
    if len(matches) != 1 or not str(matches[0].get("id", "")).strip():
        raise ImportFailure("remote safety KB must already contain one safety-policy tag")
    return str(matches[0]["id"])


def verify_preflight_document(
    client: WeKnoraClient,
    old: SafetyBundle,
    controls: ControlFiles,
) -> Mapping[str, Any]:
    expected = {
        controls.old_document_id: {
            "path": old.relative_path,
            "file_hash": old.file_md5,
            "metadata": old.remote_metadata,
        }
    }
    verify_document_exact_set(client, controls.kb_id, expected)
    rows = list_all_documents(client, controls.kb_id)
    row = rows[0]
    if str(row.get("parse_status", "")) != "completed":
        raise ImportFailure("the v5 safety document is not in completed state")
    return row


def choose_retrieval_probe(old: SafetyBundle, new: SafetyBundle) -> str:
    old_lines = old.file_path.read_text(encoding="utf-8").splitlines()
    new_lines = new.file_path.read_text(encoding="utf-8").splitlines()
    added = [
        line[2:].strip()
        for line in difflib.ndiff(old_lines, new_lines)
        if line.startswith("+ ") and line[2:].strip()
    ]
    for line in added:
        if line.startswith("#") and 8 <= len(line) <= 120:
            return line.lstrip("#").strip()
    for line in added:
        if 12 <= len(line) <= 120:
            return line
    return str(new.row.get("title") or new.base_metadata["document_id"])


def probe_retrieval(
    client: WeKnoraClient,
    kb_id: str,
    document_id: str,
    query: str,
    phase: str,
    exact_document_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    rows = envelope_data(
        client.request(
            "POST",
            "/knowledge-search",
            json_body={"query": query, "knowledge_base_ids": [kb_id]},
        ),
        f"{phase} safety retrieval",
    )
    if not isinstance(rows, list) or not rows:
        raise ImportFailure(f"{phase} safety retrieval returned no results")
    if any(
        not isinstance(row, dict) or str(row.get("knowledge_base_id", "")) != kb_id
        for row in rows
    ):
        raise ImportFailure(f"{phase} safety retrieval escaped its KB")
    result_ids = [str(row.get("knowledge_id", "")).strip() for row in rows]
    if document_id not in result_ids:
        raise ImportFailure(f"{phase} safety retrieval did not return the v6 document")
    if exact_document_ids is not None and set(result_ids) != set(exact_document_ids):
        raise ImportFailure(
            f"{phase} safety retrieval document set drifted: {sorted(set(result_ids))}"
        )
    return {
        "phase": phase,
        "query": query,
        "result_count": len(rows),
        "knowledge_ids": sorted(set(result_ids)),
    }


def upload_bundle_document(
    client: WeKnoraClient,
    bundle: SafetyBundle,
    controls: ControlFiles,
    tag_id: str,
    timeout: float,
    poll_interval: float,
) -> Dict[str, Any]:
    response = client.upload_document(
        controls.kb_id,
        bundle.file_path,
        bundle.relative_path.split("/", 1)[-1],
        bundle.remote_metadata,
        [tag_id],
        {"chunking_config": bundle.kb_spec["chunking_config"]},
    )
    server_row = envelope_data(response, f"upload {bundle.relative_path}")
    if not isinstance(server_row, dict) or not str(server_row.get("id", "")).strip():
        raise ImportFailure("safety document upload returned no document ID")
    document_id = str(server_row["id"])
    verify_document_identity(
        server_row,
        expected_id=document_id,
        kb_id=controls.kb_id,
        relative_path=bundle.relative_path,
        expected_file_hash=bundle.file_md5,
        expected_metadata=bundle.remote_metadata,
    )
    record = {
        "path": bundle.relative_path,
        "sha256": bundle.file_sha256,
        "id": document_id,
        "kb_id": controls.kb_id,
        "file_hash": bundle.file_md5,
        "metadata": bundle.remote_metadata,
        "parse_status": server_row.get("parse_status", "pending"),
    }
    wait_for_documents(client, [record], timeout, poll_interval)
    reread = envelope_data(
        client.request("GET", f"/knowledge/{document_id}"),
        f"get uploaded {bundle.relative_path}",
    )
    if not isinstance(reread, dict):
        raise ImportFailure("uploaded safety document reread is not an object")
    verify_document_identity(
        reread,
        expected_id=document_id,
        kb_id=controls.kb_id,
        relative_path=bundle.relative_path,
        expected_file_hash=bundle.file_md5,
        expected_metadata=bundle.remote_metadata,
    )
    if str(reread.get("parse_status", "")) != "completed":
        raise ImportFailure("uploaded safety document did not reach completed state")
    record["parse_status"] = "completed"
    return record


def _document_ids(client: WeKnoraClient, kb_id: str) -> List[str]:
    return [str(row.get("id", "")) for row in list_all_documents(client, kb_id)]


def wait_document_absent(
    client: WeKnoraClient,
    kb_id: str,
    document_id: str,
    timeout: float,
    poll_interval: float,
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if document_id not in _document_ids(client, kb_id):
            return
        if time.monotonic() >= deadline:
            raise ImportFailure(f"document deletion timed out: {document_id}")
        if poll_interval:
            time.sleep(poll_interval)


def delete_document(
    client: WeKnoraClient,
    kb_id: str,
    document_id: str,
    timeout: float,
    poll_interval: float,
) -> str:
    response = client.request(
        "DELETE",
        f"/knowledge/{document_id}",
        accepted=(200,),
    )
    data = envelope_data(response, f"delete document {document_id}")
    if not isinstance(data, dict) or not str(data.get("task_id", "")).strip():
        raise ImportFailure("asynchronous document deletion returned no task_id")
    wait_document_absent(client, kb_id, document_id, timeout, poll_interval)
    return str(data["task_id"])


def discover_bundle_document(
    rows: Iterable[Mapping[str, Any]],
    bundle: SafetyBundle,
    kb_id: str,
) -> Optional[Mapping[str, Any]]:
    matches: List[Mapping[str, Any]] = []
    for row in rows:
        if str(row.get("knowledge_base_id", "")) != kb_id:
            continue
        try:
            metadata = document_metadata(row.get("metadata"), "rollback document")
        except ImportFailure:
            continue
        if (
            str(row.get("file_hash", "")) == bundle.file_md5
            and metadata.get("bundle_path") == bundle.relative_path
            and metadata.get("bundle_sha256") == bundle.file_sha256
            and metadata.get("bundle_version") == bundle.version
        ):
            matches.append(row)
    if len(matches) > 1:
        raise ImportFailure("rollback found duplicate managed safety documents")
    return matches[0] if matches else None


def rollback_to_old(
    client: WeKnoraClient,
    old: SafetyBundle,
    new: SafetyBundle,
    controls: ControlFiles,
    tag_id: str,
    journal: MutationJournal,
    timeout: float,
    poll_interval: float,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {"attempted": True, "started_at": utc_now()}
    rows = list_all_documents(client, controls.kb_id)
    old_row = discover_bundle_document(rows, old, controls.kb_id)
    new_row = discover_bundle_document(rows, new, controls.kb_id)

    # Once an async old-delete may have been accepted, its currently visible
    # row is not a safe rollback anchor: the worker could remove it later.
    if journal.old_delete_may_be_inflight:
        if old_row is not None:
            wait_document_absent(
                client,
                controls.kb_id,
                str(old_row["id"]),
                timeout,
                poll_interval,
            )
        old_row = None

    if old_row is None:
        restored = upload_bundle_document(
            client,
            old,
            controls,
            tag_id,
            timeout,
            poll_interval,
        )
        restored_id = str(restored["id"])
        result["old_document"] = {"action": "reuploaded", "id": restored_id}
    else:
        restored_id = str(old_row["id"])
        verify_document_identity(
            old_row,
            expected_id=restored_id,
            kb_id=controls.kb_id,
            relative_path=old.relative_path,
            expected_file_hash=old.file_md5,
            expected_metadata=old.remote_metadata,
        )
        if str(old_row.get("parse_status", "")) != "completed":
            raise ImportFailure("rollback v5 document is not completed")
        result["old_document"] = {"action": "preserved", "id": restored_id}

    rows = list_all_documents(client, controls.kb_id)
    new_row = discover_bundle_document(rows, new, controls.kb_id)
    if new_row is not None:
        new_id = str(new_row["id"])
        result["new_delete_task_id"] = delete_document(
            client,
            controls.kb_id,
            new_id,
            timeout,
            poll_interval,
        )
        result["new_document"] = {"action": "deleted", "id": new_id}
    else:
        result["new_document"] = {"action": "absent"}

    verify_document_exact_set(
        client,
        controls.kb_id,
        {
            restored_id: {
                "path": old.relative_path,
                "file_hash": old.file_md5,
                "metadata": old.remote_metadata,
            }
        },
    )
    final_row = list_all_documents(client, controls.kb_id)[0]
    if str(final_row.get("parse_status", "")) != "completed":
        raise ImportFailure("rollback exact-set document is not completed")
    result.update(
        {
            "status": "restored_v5",
            "completed_at": utc_now(),
            "exact_set_ids": [restored_id],
        }
    )
    return result


def _safe_exception(exc: BaseException) -> Dict[str, str]:
    if isinstance(exc, APIError):
        message = f"HTTP {exc.status} {exc.method} {exc.url}"
    else:
        message = str(exc)
    api_key = os.environ.get("WEKNORA_API_KEY", "")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    message = re.sub(r"sk-[A-Za-z0-9._~+/=-]{6,}", "[REDACTED]", message)
    return {"type": type(exc).__name__, "message": message[:1000]}


def _receipt_base(
    client: WeKnoraClient,
    old: SafetyBundle,
    new: SafetyBundle,
    controls: ControlFiles,
    server: Optional[Mapping[str, Any]],
    journal: MutationJournal,
) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "receipt_type": "runtime_safety_delta",
        "base_url": client.base_url,
        "tenant_partition": "runtime",
        "tenant": dict(controls.tenant),
        "server": dict(server or {}),
        "from_bundle": {
            "bundle_version": old.version,
            "bundle_manifest_sha256": old.manifest_sha256,
            "safety_document_sha256": old.file_sha256,
            "safety_document_md5": old.file_md5,
        },
        "to_bundle": {
            "bundle_version": new.version,
            "bundle_manifest_sha256": new.manifest_sha256,
            "safety_document_sha256": new.file_sha256,
            "safety_document_md5": new.file_md5,
        },
        "control_inputs": {
            "runtime_receipt_sha256": controls.receipt_sha256,
            "runtime_state_sha256": controls.state_sha256,
        },
        "knowledge_base": {
            "key": SAFETY_KEY,
            "id": controls.kb_id,
            "name": old.kb_spec["name"],
        },
        "started_at": journal.started_at,
        "authentication": {
            "source": "WEKNORA_API_KEY environment",
            "plaintext_recorded": False,
        },
    }


def write_receipt_0600(path: Path, value: Mapping[str, Any]) -> None:
    path = path.absolute()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise ImportFailure("delta receipt parent must be a regular directory")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ImportFailure("delta receipt path must be a regular file")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
        os.chmod(path, 0o600)
        directory_fd = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ImportFailure("delta receipt permissions are not 0600")


@contextmanager
def exclusive_receipt_lock(path: Path) -> Iterator[None]:
    lock_path = path.absolute().with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise ImportFailure("delta receipt lock must not be a symlink")
    descriptor = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ImportFailure("another safety delta sync is already running") from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def apply_safety_delta(
    *,
    client: WeKnoraClient,
    old_bundle: Path,
    new_bundle: Path,
    runtime_receipt: Path,
    state: Path,
    output_receipt: Path,
    expected_tenant: str,
    wait_timeout: float = 600.0,
    poll_interval: float = 2.0,
) -> Dict[str, Any]:
    if wait_timeout <= 0 or poll_interval < 0 or poll_interval > 30:
        raise ImportFailure("invalid wait timeout or poll interval")
    output_receipt = output_receipt.absolute()
    inputs = {
        old_bundle.absolute(),
        new_bundle.absolute(),
        runtime_receipt.absolute(),
        state.absolute(),
    }
    if output_receipt in inputs:
        raise ImportFailure("delta receipt output must differ from every input")
    for bundle_path in (old_bundle.absolute(), new_bundle.absolute()):
        try:
            output_receipt.relative_to(bundle_path)
        except ValueError:
            continue
        raise ImportFailure("delta receipt output must not be inside an input bundle")
    if not expected_tenant:
        raise ImportFailure("EXPECTED_TENANT is required")

    journal = MutationJournal()
    server: Optional[Mapping[str, Any]] = None
    old: Optional[SafetyBundle] = None
    new: Optional[SafetyBundle] = None
    controls: Optional[ControlFiles] = None
    tag_id = ""

    with exclusive_receipt_lock(output_receipt), ExitStack() as stack:
        old_snapshot = stack.enter_context(immutable_bundle_snapshot(old_bundle))
        new_snapshot = stack.enter_context(immutable_bundle_snapshot(new_bundle))
        try:
            journal.phase = "validating_inputs"
            old = load_safety_bundle(old_snapshot, "old")
            new = load_safety_bundle(new_snapshot, "new")
            validate_delta_shape(old, new)
            controls = validate_control_files(
                runtime_receipt.absolute(),
                state.absolute(),
                old,
                client.base_url,
                expected_tenant,
            )

            journal.phase = "remote_preflight"
            server = verify_v072_legacy_server(client)
            verify_remote_tenant(client, controls.tenant)
            verify_remote_kb(client, old, controls)
            tag_id = existing_safety_tag_id(client, controls.kb_id)
            verify_preflight_document(client, old, controls)

            journal.phase = "uploading_v6"
            journal.mutation_started = True
            new_record = upload_bundle_document(
                client,
                new,
                controls,
                tag_id,
                wait_timeout,
                poll_interval,
            )
            journal.new_document_id = str(new_record["id"])
            query = choose_retrieval_probe(old, new)
            journal.retrieval_checks.append(
                probe_retrieval(
                    client,
                    controls.kb_id,
                    journal.new_document_id,
                    query,
                    "pre-delete",
                )
            )

            journal.phase = "deleting_v5"
            journal.old_delete_attempted = True
            journal.old_delete_may_be_inflight = True
            try:
                journal.old_delete_task_id = delete_document(
                    client,
                    controls.kb_id,
                    controls.old_document_id,
                    wait_timeout,
                    poll_interval,
                )
            except APIError as exc:
                if 400 <= exc.status < 500:
                    journal.old_delete_may_be_inflight = False
                raise

            journal.phase = "final_verification"
            verify_document_exact_set(
                client,
                controls.kb_id,
                {
                    journal.new_document_id: {
                        "path": new.relative_path,
                        "file_hash": new.file_md5,
                        "metadata": new.remote_metadata,
                    }
                },
            )
            final_row = list_all_documents(client, controls.kb_id)[0]
            if str(final_row.get("parse_status", "")) != "completed":
                raise ImportFailure("final v6 safety document is not completed")
            journal.retrieval_checks.append(
                probe_retrieval(
                    client,
                    controls.kb_id,
                    journal.new_document_id,
                    query,
                    "post-delete",
                    exact_document_ids=[journal.new_document_id],
                )
            )

            journal.phase = "writing_receipt"
            receipt = _receipt_base(client, old, new, controls, server, journal)
            receipt.update(
                {
                    "status": "passed",
                    "completed_at": utc_now(),
                    "documents": {
                        "old": {
                            "id": controls.old_document_id,
                            "delete_task_id": journal.old_delete_task_id,
                            "final_state": "absent",
                        },
                        "new": {
                            "id": journal.new_document_id,
                            "parse_status": "completed",
                            "remote_identity_verified": True,
                        },
                    },
                    "exact_set": {
                        "verified": True,
                        "document_count": 1,
                        "document_ids": [journal.new_document_id],
                    },
                    "retrieval_checks": journal.retrieval_checks,
                    "rollback": journal.rollback,
                }
            )
            write_receipt_0600(output_receipt, receipt)
            return receipt
        except BaseException as exc:
            original = exc
            failure_phase = journal.phase
            rollback_error: Optional[BaseException] = None
            if (
                journal.mutation_started
                and old is not None
                and new is not None
                and controls is not None
                and tag_id
            ):
                journal.phase = "rollback"
                journal.rollback = {"attempted": True, "status": "in_progress"}
                try:
                    journal.rollback = rollback_to_old(
                        client,
                        old,
                        new,
                        controls,
                        tag_id,
                        journal,
                        wait_timeout,
                        poll_interval,
                    )
                except BaseException as caught:
                    rollback_error = caught
                    journal.rollback = {
                        "attempted": True,
                        "status": "failed",
                        "error": _safe_exception(caught),
                    }

            if old is not None and new is not None and controls is not None:
                failed_receipt = _receipt_base(client, old, new, controls, server, journal)
            else:
                failed_receipt = {
                    "schema_version": 1,
                    "receipt_type": "runtime_safety_delta",
                    "base_url": client.base_url,
                    "started_at": journal.started_at,
                    "authentication": {
                        "source": "WEKNORA_API_KEY environment",
                        "plaintext_recorded": False,
                    },
                }
            failed_receipt.update(
                {
                    "status": "failed",
                    "failed_at": utc_now(),
                    "failed_phase": failure_phase,
                    "error": _safe_exception(original),
                    "rollback": journal.rollback,
                    "documents": {
                        "old_id": controls.old_document_id if controls else "",
                        "new_id": journal.new_document_id,
                        "old_delete_task_id": journal.old_delete_task_id,
                    },
                    "retrieval_checks": journal.retrieval_checks,
                }
            )
            receipt_error: Optional[BaseException] = None
            try:
                write_receipt_0600(output_receipt, failed_receipt)
            except BaseException as caught:
                receipt_error = caught
            if hasattr(original, "add_note"):
                if rollback_error is not None:
                    original.add_note(f"rollback failed: {_safe_exception(rollback_error)['message']}")
                if receipt_error is not None:
                    original.add_note(f"failed receipt could not be written: {_safe_exception(receipt_error)['message']}")
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-bundle", type=Path, required=True)
    parser.add_argument("--new-bundle", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("WEKNORA_URL", DEFAULT_BASE_URL))
    parser.add_argument("--runtime-receipt", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output-delta-receipt", type=Path, required=True)
    parser.add_argument("--wait-timeout", type=float, default=600.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=120.0)
    parser.add_argument("--apply", action="store_true", help="required to perform the remote delta")
    return parser


def safe_error_text(exc: BaseException) -> str:
    return _safe_exception(exc)["message"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.apply:
        print("refusing to mutate without --apply", file=sys.stderr)
        return 2
    api_key = os.environ.get("WEKNORA_API_KEY", "").strip()
    expected_tenant = os.environ.get("EXPECTED_TENANT", "").strip()
    if not api_key or not expected_tenant:
        print("sync failed: WEKNORA_API_KEY and EXPECTED_TENANT are required", file=sys.stderr)
        return 2
    try:
        if args.http_timeout <= 0:
            raise ImportFailure("--http-timeout must be positive")
        base_url = normalize_loopback_base_url(args.base_url)
        client = WeKnoraClient(base_url, api_key=api_key, timeout=args.http_timeout)
        receipt = apply_safety_delta(
            client=client,
            old_bundle=args.old_bundle,
            new_bundle=args.new_bundle,
            runtime_receipt=args.runtime_receipt,
            state=args.state,
            output_receipt=args.output_delta_receipt,
            expected_tenant=expected_tenant,
            wait_timeout=args.wait_timeout,
            poll_interval=args.poll_interval,
        )
        print(
            json.dumps(
                {
                    "status": receipt["status"],
                    "receipt": str(args.output_delta_receipt.absolute()),
                    "secrets_printed": False,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (APIError, ImportFailure, FileNotFoundError, KeyError, OSError, ValueError) as exc:
        print(f"sync failed: {safe_error_text(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
