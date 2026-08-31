#!/usr/bin/env python3
"""Create and verify least-privilege runtime retrieve keys with an Owner JWT."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from approve_faq import faq_snapshot
from import_bundle import (
    APIError,
    DEFAULT_BUNDLE,
    DEFAULT_RECEIPT_AUDIT,
    DEFAULT_RECEIPT_RUNTIME,
    ImportFailure,
    WeKnoraClient,
    envelope_data,
    flatten_page_data,
    get_current_tenant,
    list_all_faq_entries,
    read_json,
    read_jsonl,
)
from verify_bundle import BundleValidationError, validate_bundle


MIGRATION_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = MIGRATION_DIR / "runtime_access_keys.json"
APPROVAL_TIMEZONE = timezone(timedelta(hours=8))


def parse_approval_date(value: Any, field: str, scope: str) -> date:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError as exc:
        raise ImportFailure(f"{scope} approval has invalid {field}") from exc


def approval_expiry_unix(value: date) -> int:
    end_of_day = datetime.combine(
        value + timedelta(days=1),
        datetime_time.min,
        APPROVAL_TIMEZONE,
    ) - timedelta(seconds=1)
    return int(end_of_day.timestamp())


def parse_rfc3339_unix(value: Any, field: str) -> int:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ImportFailure(f"invalid {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ImportFailure(f"{field} must include a timezone: {value!r}")
    return int(parsed.timestamp())


def write_secret_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(str(temporary), str(path))
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_receipt(receipt: Mapping[str, Any], partition: str) -> None:
    if receipt.get("status") != "passed" or receipt.get("tenant_partition") != partition:
        raise ImportFailure(f"{partition} import receipt is missing or not passed")
    if not str(receipt.get("tenant", {}).get("id", "")):
        raise ImportFailure(f"{partition} import receipt has no tenant ID")


def require_approval(
    path: Path,
    expected_scope: str,
    runtime_receipt: Mapping[str, Any],
    bundle: Path,
) -> Dict[str, Any]:
    approval = read_json(path)
    if approval.get("status") != "passed" or approval.get("scope") != expected_scope:
        raise ImportFailure(f"approval receipt is not passed for {expected_scope}: {path}")
    if approval.get("bundle_version") != runtime_receipt.get("bundle_version"):
        raise ImportFailure(f"approval receipt belongs to another bundle: {path}")
    if approval.get("bundle_manifest_sha256") != runtime_receipt.get("bundle_manifest_sha256"):
        raise ImportFailure(f"approval receipt belongs to different bundle content: {path}")
    if str(approval.get("tenant", {}).get("id", "")) != str(
        runtime_receipt.get("tenant", {}).get("id", "")
    ):
        raise ImportFailure(f"approval receipt belongs to another tenant: {path}")
    if str(approval.get("base_url", "")).rstrip("/") != str(
        runtime_receipt.get("base_url", "")
    ).rstrip("/"):
        raise ImportFailure(f"approval receipt belongs to another server: {path}")
    kb_key = {
        "customer": "customer_approved",
        "safety-boundary": "safety_boundary",
    }[expected_scope]
    if str(approval.get("knowledge_base_id", "")) != str(
        runtime_receipt.get("knowledge_bases", {}).get(kb_key, {}).get("id", "")
    ):
        raise ImportFailure(f"approval receipt belongs to another knowledge base: {path}")
    bundle_key = {
        "customer": "customer_approved",
        "safety-boundary": "safety_boundary",
    }[expected_scope]
    metadata = read_jsonl(bundle / bundle_key / "faq_metadata.jsonl")
    metadata_by_id = {str(row.get("external_id", "")): row for row in metadata}
    receipt_rows = approval.get("approvals", [])
    if not isinstance(receipt_rows, list):
        raise ImportFailure(f"approval receipt has no approval rows: {path}")
    receipt_by_id = {str(row.get("external_id", "")): row for row in receipt_rows}
    if len(receipt_by_id) != len(receipt_rows) or set(receipt_by_id) != set(metadata_by_id):
        raise ImportFailure(f"approval receipt rows do not match the verified bundle: {path}")
    for external_id, metadata_row in metadata_by_id.items():
        row = receipt_by_id[external_id]
        if str(row.get("content_sha256", "")) != str(metadata_row.get("content_sha256", "")):
            raise ImportFailure(f"{external_id}: approval content hash no longer matches bundle")
        if str(row.get("standard_question", "")).strip() != str(
            metadata_row.get("standard_question", "")
        ).strip():
            raise ImportFailure(f"{external_id}: approval question no longer matches bundle")
    approved_rows = [
        row
        for row in approval.get("approvals", [])
        if str(row.get("decision", "")).lower() == "approved"
    ]
    if int(approval.get("enabled_count", 0)) < 1 or len(approved_rows) != int(
        approval.get("enabled_count", 0)
    ):
        raise ImportFailure(f"approval receipt enables no entries: {path}")
    if any(not str(row.get("standard_question", "")).strip() for row in approved_rows):
        raise ImportFailure(f"approval receipt lacks approved standard_question values: {path}")
    today = datetime.now(APPROVAL_TIMEZONE).date()
    expiry_values: List[int] = []
    for row in approved_rows:
        external_id = str(row.get("external_id", "")).strip() or expected_scope
        owner = str(row.get("review_owner", "")).strip()
        if not owner or owner.lower() == "unassigned":
            raise ImportFailure(f"{external_id}: approved receipt has no review_owner")
        verified = parse_approval_date(
            row.get("last_verified_at"),
            "last_verified_at",
            external_id,
        )
        effective = parse_approval_date(row.get("effective_from"), "effective_from", external_id)
        expires = parse_approval_date(row.get("expires_on"), "expires_on", external_id)
        if verified > today or effective > today or expires < today or effective > expires:
            raise ImportFailure(f"{external_id}: approval is not currently effective")
        needs_secondary = (
            expected_scope == "safety-boundary"
            or metadata_by_id[external_id].get("risk_level") == "高"
        )
        if needs_secondary:
            secondary = str(row.get("secondary_review_owner", "")).strip()
            if (
                not secondary
                or secondary.lower() == "unassigned"
                or secondary.casefold() == owner.casefold()
            ):
                raise ImportFailure(f"{external_id}: independent secondary reviewer is required")
        expiry_values.append(approval_expiry_unix(expires))
    result = dict(approval)
    result["_approved_expiry_unix"] = min(expiry_values)
    result["_positive_query"] = str(approved_rows[0]["standard_question"]).strip()
    return result


def verify_live_approval(
    owner: WeKnoraClient,
    approval: Mapping[str, Any],
    context: str,
) -> Dict[str, Any]:
    kb_id = str(approval.get("knowledge_base_id", ""))
    expected = approval.get("faq_snapshot")
    if not kb_id or not isinstance(expected, dict) or not expected.get("sha256"):
        raise ImportFailure(f"{context}: approval receipt has no canonical FAQ snapshot")
    rows = list_all_faq_entries(owner, kb_id)
    actual = faq_snapshot(rows, f"{context} live FAQ")
    if actual != expected:
        raise ImportFailure(
            f"{context}: live FAQ snapshot differs from the approved snapshot; rerun approval"
        )
    if actual["enabled_count"] != int(approval.get("enabled_count", -1)):
        raise ImportFailure(f"{context}: enabled FAQ count differs from approval receipt")
    return actual


def key_specs(
    receipt: Mapping[str, Any],
    staff_name: str,
    customer_name: str,
    create_customer: bool,
    include_boundary: bool,
    requested_expires_at: int,
    customer_positive_query: str = "",
    customer_approval_expires_at: int = 0,
    customer_enabled_chunk_ids: Sequence[str] = (),
    boundary_positive_query: str = "",
    boundary_approval_expires_at: int = 0,
    boundary_enabled_chunk_ids: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    kbs = receipt["knowledge_bases"]
    boundary = [str(kbs["safety_boundary"]["id"])] if include_boundary else []
    staff_expires_at = min(
        value
        for value in (requested_expires_at, boundary_approval_expires_at or requested_expires_at)
    )
    staff_positive_checks = [
        {
            "kb_id": str(kbs["safety_policy"]["id"]),
            "query": "安全规范与服务流程",
        }
    ]
    if include_boundary:
        staff_positive_checks.append(
            {
                "kb_id": str(kbs["safety_boundary"]["id"]),
                "query": boundary_positive_query,
                "expected_chunk_ids": list(boundary_enabled_chunk_ids),
            }
        )
    specs = [
        {
            "key": "staff",
            "name": staff_name,
            "full_access": False,
            "knowledge_base_ids": [
                str(kbs["staff_courses"]["id"]),
                str(kbs["safety_policy"]["id"]),
                *boundary,
            ],
            "capabilities": ["retrieve"],
            "expires_at_unix": staff_expires_at,
            "positive_checks": staff_positive_checks,
            "forbidden_kb_id": str(kbs["customer_approved"]["id"]),
        }
    ]
    if create_customer:
        customer_expiry_candidates = [requested_expires_at, customer_approval_expires_at]
        if include_boundary:
            customer_expiry_candidates.append(boundary_approval_expires_at)
        customer_positive_checks = [
            {
                "kb_id": str(kbs["customer_approved"]["id"]),
                "query": customer_positive_query,
                "expected_chunk_ids": list(customer_enabled_chunk_ids),
            }
        ]
        if include_boundary:
            customer_positive_checks.append(
                {
                    "kb_id": str(kbs["safety_boundary"]["id"]),
                    "query": boundary_positive_query,
                    "expected_chunk_ids": list(boundary_enabled_chunk_ids),
                }
            )
        specs.append(
            {
                "key": "customer",
                "name": customer_name,
                "full_access": False,
                "knowledge_base_ids": [
                    str(kbs["customer_approved"]["id"]),
                    *boundary,
                ],
                "capabilities": ["retrieve"],
                "expires_at_unix": min(customer_expiry_candidates),
                "positive_checks": customer_positive_checks,
                "forbidden_kb_id": str(kbs["staff_courses"]["id"]),
            }
        )
    for spec in specs:
        spec["knowledge_base_ids"] = list(dict.fromkeys(spec["knowledge_base_ids"]))
        if not spec["knowledge_base_ids"]:
            raise ImportFailure(f"{spec['key']} key has an empty KB allow-list")
        checks = spec.get("positive_checks", [])
        if not checks or any(
            not str(row.get("kb_id", "")).strip()
            or not str(row.get("query", "")).strip()
            or (
                "expected_chunk_ids" in row
                and not [item for item in row.get("expected_chunk_ids", []) if str(item).strip()]
            )
            for row in checks
        ):
            raise ImportFailure(f"{spec['key']} key has an invalid positive-test query")
        if int(spec["expires_at_unix"]) <= int(time.time()):
            raise ImportFailure(f"{spec['key']} key would already be expired")
    return specs


def public_key_payload(spec: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "name": spec["name"],
        "full_access": False,
        "knowledge_base_ids": spec["knowledge_base_ids"],
        "capabilities": ["retrieve"],
        "expires_at_unix": spec["expires_at_unix"],
    }


def verify_key_shape(
    row: Mapping[str, Any],
    spec: Mapping[str, Any],
    require_exact_expiry: bool = False,
) -> None:
    if str(row.get("scope_type", "")).lower() != "tenant":
        raise ImportFailure(f"{spec['name']}: scope_type must be tenant")
    if bool(row.get("full_access")):
        raise ImportFailure(f"{spec['name']}: full_access must be false")
    if set(row.get("capabilities", [])) != {"retrieve"}:
        raise ImportFailure(f"{spec['name']}: capabilities must be exactly ['retrieve']")
    actual_ids = {str(item) for item in row.get("knowledge_base_ids", [])}
    expected_ids = set(spec["knowledge_base_ids"])
    if not actual_ids or actual_ids != expected_ids:
        raise ImportFailure(
            f"{spec['name']}: KB allow-list mismatch; expected={sorted(expected_ids)}, "
            f"actual={sorted(actual_ids)}"
        )
    actual_expiry = parse_rfc3339_unix(row.get("expires_at"), "expires_at")
    expected_max = int(spec["expires_at_unix"])
    if actual_expiry <= int(time.time()):
        raise ImportFailure(f"{spec['name']}: existing API key is expired")
    if actual_expiry > expected_max or (require_exact_expiry and actual_expiry != expected_max):
        raise ImportFailure(
            f"{spec['name']}: expiry exceeds or differs from the approved limit; "
            f"limit={spec['expires_at_unix']}, "
            f"actual={actual_expiry}"
        )


def resolve_created_token(row: Mapping[str, Any], context: str) -> str:
    token = str(row.get("token", "")).strip()
    if not token:
        raise ImportFailure(f"{context}: create response returned no plaintext token")
    return token


def resolve_listed_token(
    row: Mapping[str, Any],
    saved: Mapping[str, Any],
    context: str,
) -> str:
    server_token = str(row.get("api_key", "")).strip()
    saved_token = str(saved.get("token", "")).strip()
    if saved_token and str(saved.get("id", "")) != str(row.get("id", "")):
        raise ImportFailure(f"{context}: saved token belongs to another API key ID")
    if server_token and saved_token and not hmac.compare_digest(server_token, saved_token):
        raise ImportFailure(f"{context}: saved token differs from the server's API key value")
    token = server_token or saved_token
    if not token:
        raise ImportFailure(f"{context}: server returned no reusable API key value")
    return token


def expect_forbidden(
    client: WeKnoraClient,
    method: str,
    path: str,
    body: Any,
    required_markers: Sequence[str],
) -> None:
    try:
        client.request(method, path, json_body=body)
    except APIError as exc:
        error_text = json.dumps(exc.payload, ensure_ascii=False).casefold()
        if exc.status == 403 and all(marker.casefold() in error_text for marker in required_markers):
            return
        raise ImportFailure(
            f"expected the scoped-key 403 contract, got HTTP {exc.status}: {method} {path}"
        ) from exc
    raise ImportFailure(f"least-privilege negative test unexpectedly succeeded: {method} {path}")


def verify_runtime_key(
    base_url: str,
    token: str,
    tenant_id: str,
    spec: Mapping[str, Any],
    audit_kb_id: str,
) -> Dict[str, Any]:
    client = WeKnoraClient(base_url, token)
    tenant = get_current_tenant(client)
    if tenant["id"] != tenant_id:
        raise ImportFailure(f"{spec['name']}: key belongs to a different tenant")
    listed = flatten_page_data(
        envelope_data(client.request("GET", "/knowledge-bases"), "list scoped KBs"),
        "list scoped KBs",
    )
    listed_ids = {str(row.get("id", "")) for row in listed}
    if listed_ids != set(spec["knowledge_base_ids"]):
        raise ImportFailure(
            f"{spec['name']}: scoped KB listing mismatch: {sorted(listed_ids)}"
        )
    positive_counts: Dict[str, int] = {}
    for check in spec["positive_checks"]:
        kb_id = str(check["kb_id"])
        positive = envelope_data(
            client.request(
                "POST",
                "/knowledge-search",
                json_body={
                    "query": check["query"],
                    "knowledge_base_ids": [kb_id],
                },
            ),
            f"{spec['name']} positive retrieval",
        )
        if not isinstance(positive, list) or not positive:
            raise ImportFailure(f"{spec['name']}: positive retrieval returned no results for {kb_id}")
        if any(str(row.get("knowledge_base_id", "")) != kb_id for row in positive):
            raise ImportFailure(f"{spec['name']}: positive retrieval escaped KB {kb_id}")
        expected_chunks = {str(item) for item in check.get("expected_chunk_ids", [])}
        if expected_chunks and not any(str(row.get("id", "")) in expected_chunks for row in positive):
            raise ImportFailure(
                f"{spec['name']}: positive FAQ retrieval did not return an approved chunk for {kb_id}"
            )
        positive_counts[kb_id] = len(positive)
    expect_forbidden(
        client,
        "POST",
        "/knowledge-search",
        {
            "query": "越权测试",
            "knowledge_base_ids": [spec["forbidden_kb_id"]],
        },
        ("1002", "scope"),
    )
    if audit_kb_id:
        expect_forbidden(
            client,
            "POST",
            "/knowledge-search",
            {"query": "审计越权测试", "knowledge_base_ids": [audit_kb_id]},
            ("1002", "scope"),
        )
    expect_forbidden(
        client,
        "POST",
        "/knowledge-bases",
        {"name": "MUST-NOT-BE-CREATED", "type": "document"},
        ("api key scope", "allow"),
    )
    return {
        "tenant_id": tenant_id,
        "listed_knowledge_base_ids": sorted(listed_ids),
        "positive_result_counts": positive_counts,
        "forbidden_runtime_kb": spec["forbidden_kb_id"],
        "forbidden_audit_kb": audit_kb_id,
        "mutation_forbidden": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-receipt", type=Path, default=DEFAULT_RECEIPT_RUNTIME)
    parser.add_argument("--audit-receipt", type=Path, default=DEFAULT_RECEIPT_AUDIT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--customer-approval-receipt", type=Path)
    parser.add_argument("--boundary-approval-receipt", type=Path)
    parser.add_argument("--create-customer", action="store_true")
    parser.add_argument("--include-boundary", action="store_true")
    parser.add_argument("--staff-key-name", default="training-staff-retrieve")
    parser.add_argument("--customer-key-name", default="customer-approved-retrieve")
    parser.add_argument("--expires-days", type=int, default=90)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=os.environ.get("WEKNORA_URL", ""))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        args.bundle = args.bundle.resolve()
        validation = validate_bundle(args.bundle)
        runtime = read_json(args.runtime_receipt)
        audit = read_json(args.audit_receipt)
        validate_receipt(runtime, "runtime")
        validate_receipt(audit, "audit")
        if runtime.get("bundle_version") != audit.get("bundle_version"):
            raise ImportFailure("runtime and audit receipts belong to different bundles")
        if runtime.get("bundle_version") != validation["bundle_version"]:
            raise ImportFailure("runtime receipt belongs to a different local bundle")
        if runtime.get("bundle_manifest_sha256") != validation["bundle_manifest_sha256"]:
            raise ImportFailure("runtime receipt belongs to different local bundle content")
        if audit.get("bundle_manifest_sha256") != validation["bundle_manifest_sha256"]:
            raise ImportFailure("audit receipt belongs to different local bundle content")
        if str(runtime["tenant"]["id"]) == str(audit["tenant"]["id"]):
            raise ImportFailure("runtime and audit receipts use the same tenant")
        base_url = (args.base_url or str(runtime.get("base_url", ""))).rstrip("/")
        if (
            not base_url
            or str(runtime.get("base_url", "")).rstrip("/") != base_url
            or str(audit.get("base_url", "")).rstrip("/") != base_url
        ):
            raise ImportFailure("runtime and audit receipts must use the same server")
        customer_approval: Dict[str, Any] = {}
        if args.create_customer:
            if not args.customer_approval_receipt:
                raise ImportFailure("--create-customer requires --customer-approval-receipt")
            customer_approval = require_approval(
                args.customer_approval_receipt,
                "customer",
                runtime,
                args.bundle,
            )
        boundary_approval: Dict[str, Any] = {}
        if args.include_boundary:
            if not args.boundary_approval_receipt:
                raise ImportFailure("--include-boundary requires --boundary-approval-receipt")
            boundary_approval = require_approval(
                args.boundary_approval_receipt,
                "safety-boundary",
                runtime,
                args.bundle,
            )
        if args.expires_days < 1 or args.expires_days > 365:
            raise ImportFailure("--expires-days must be between 1 and 365")
        requested_expires_at = int(time.time()) + args.expires_days * 86400
        customer_positive_query = str(customer_approval.get("_positive_query", ""))
        boundary_positive_query = str(boundary_approval.get("_positive_query", ""))
        customer_chunks = [
            str(row.get("chunk_id", ""))
            for row in customer_approval.get("faq_snapshot", {}).get("enabled_entries", [])
        ]
        boundary_chunks = [
            str(row.get("chunk_id", ""))
            for row in boundary_approval.get("faq_snapshot", {}).get("enabled_entries", [])
        ]
        specs = key_specs(
            runtime,
            args.staff_key_name,
            args.customer_key_name,
            args.create_customer,
            args.include_boundary,
            requested_expires_at,
            customer_positive_query,
            int(customer_approval.get("_approved_expiry_unix", 0)),
            customer_chunks,
            boundary_positive_query,
            int(boundary_approval.get("_approved_expiry_unix", 0)),
            boundary_chunks,
        )
        plan = {
            "mode": "apply" if args.apply else "plan",
            "tenant_id": str(runtime["tenant"]["id"]),
            "keys": [
                {
                    "name": spec["name"],
                    "full_access": False,
                    "capabilities": ["retrieve"],
                    "knowledge_base_ids": spec["knowledge_base_ids"],
                    "expires_at_unix": spec["expires_at_unix"],
                }
                for spec in specs
            ],
        }
        if not args.apply:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        owner_jwt = os.environ.get("WEKNORA_OWNER_JWT", "")
        if not owner_jwt:
            raise ImportFailure("WEKNORA_OWNER_JWT is required for --apply")
        owner = WeKnoraClient(base_url, bearer_token=owner_jwt)
        tenant = get_current_tenant(owner)
        tenant_id = str(runtime["tenant"]["id"])
        if tenant["id"] != tenant_id:
            raise ImportFailure("Owner JWT active tenant does not match runtime receipt")
        if customer_approval:
            verify_live_approval(owner, customer_approval, "customer approval")
        if boundary_approval:
            verify_live_approval(owner, boundary_approval, "safety-boundary approval")
        audit_kb_id = str(audit.get("knowledge_bases", {}).get("audit_raw", {}).get("id", ""))
        if not audit_kb_id:
            raise ImportFailure("audit receipt has no audit_raw knowledge-base ID")
        existing = flatten_page_data(
            envelope_data(
                owner.request("GET", f"/tenants/{tenant_id}/api-keys"),
                "list tenant API keys",
            ),
            "list tenant API keys",
        )
        secret_state: Dict[str, Any] = (
            read_json(args.output) if args.output.is_file() else {"keys": {}}
        )
        secret_state.setdefault("keys", {})
        if secret_state.get("server") and str(secret_state.get("server", "")).rstrip("/") != base_url:
            raise ImportFailure("existing secret file belongs to another server")
        if secret_state.get("tenant") and str(
            secret_state.get("tenant", {}).get("id", "")
        ) != tenant_id:
            raise ImportFailure("existing secret file belongs to another tenant")
        summaries: List[Dict[str, Any]] = []
        managed_keys: List[Dict[str, Any]] = []
        for spec in specs:
            created_id = ""
            matches = [row for row in existing if row.get("name") == spec["name"]]
            had_name_before = bool(matches)
            preexisting_ids = {str(row.get("id", "")) for row in existing}
            try:
                if len(matches) > 1:
                    raise ImportFailure(f"ambiguous existing API key name: {spec['name']}")
                saved = secret_state["keys"].get(spec["key"], {})
                if matches:
                    row = matches[0]
                    verify_key_shape(row, spec)
                    token = resolve_listed_token(row, saved, spec["name"])
                    reused = True
                else:
                    created = envelope_data(
                        owner.request(
                            "POST",
                            f"/tenants/{tenant_id}/api-keys",
                            json_body=public_key_payload(spec),
                            accepted=(201,),
                        ),
                        f"create API key {spec['name']}",
                    )
                    if not isinstance(created, dict) or not created.get("id"):
                        raise ImportFailure(f"create API key returned no ID: {spec['name']}")
                    created_id = str(created["id"])
                    create_token = resolve_created_token(created, spec["name"])
                    refreshed = flatten_page_data(
                        envelope_data(
                            owner.request("GET", f"/tenants/{tenant_id}/api-keys"),
                            "re-read tenant API keys",
                        ),
                        "re-read tenant API keys",
                    )
                    matches = [row for row in refreshed if row.get("name") == spec["name"]]
                    if len(matches) != 1 or str(matches[0].get("id", "")) != created_id:
                        raise ImportFailure(f"concurrent or ambiguous API key creation: {spec['name']}")
                    row = matches[0]
                    verify_key_shape(row, spec, require_exact_expiry=True)
                    token = resolve_listed_token(
                        row,
                        {"id": created_id, "token": create_token},
                        spec["name"],
                    )
                    existing = refreshed
                    reused = False
                secret_state["keys"][spec["key"]] = {
                    "id": row["id"],
                    "name": spec["name"],
                    "token": token,
                }
                secret_state.update(
                    {
                        "server": base_url,
                        "tenant": tenant,
                        "warning": "Secret file: chmod 0600; never commit or copy to a browser.",
                    }
                )
                write_secret_json(args.output, secret_state)
                verification = verify_runtime_key(base_url, token, tenant_id, spec, audit_kb_id)
            except (APIError, ImportFailure, KeyError, OSError, ValueError) as exc:
                discovery_error = ""
                if not created_id and not had_name_before:
                    try:
                        after_error = flatten_page_data(
                            envelope_data(
                                owner.request("GET", f"/tenants/{tenant_id}/api-keys"),
                                "discover API key after ambiguous create failure",
                            ),
                            "discover API key after ambiguous create failure",
                        )
                        candidates = [
                            row
                            for row in after_error
                            if row.get("name") == spec["name"]
                            and str(row.get("id", "")) not in preexisting_ids
                        ]
                        if len(candidates) == 1:
                            created_id = str(candidates[0]["id"])
                        elif len(candidates) > 1:
                            discovery_error = (
                                "multiple new same-name keys appeared; refusing to guess which one to revoke"
                            )
                    except (APIError, ImportFailure, KeyError, ValueError) as discover_exc:
                        discovery_error = f"could not re-list keys after create failure: {discover_exc}"
                if created_id:
                    try:
                        owner.request(
                            "DELETE",
                            f"/tenants/{tenant_id}/api-keys/{created_id}",
                        )
                        secret_state["keys"].pop(spec["key"], None)
                        write_secret_json(args.output, secret_state)
                    except (APIError, ImportFailure, OSError) as rollback_exc:
                        raise ImportFailure(
                            f"{exc}; rollback of new API key {created_id} also failed: {rollback_exc}"
                        ) from exc
                if discovery_error:
                    raise ImportFailure(f"{exc}; {discovery_error}") from exc
                raise
            summaries.append(
                {
                    "key": spec["key"],
                    "id": row["id"],
                    "name": spec["name"],
                    "reused": reused,
                    "full_access": False,
                    "capabilities": ["retrieve"],
                    "knowledge_base_ids": spec["knowledge_base_ids"],
                    "expires_at_unix": parse_rfc3339_unix(row.get("expires_at"), "expires_at"),
                    "approved_expiry_limit_unix": spec["expires_at_unix"],
                    "verification": verification,
                }
            )
            managed_keys.append(
                {
                    "key": spec["key"],
                    "id": str(row["id"]),
                    "knowledge_base_ids": list(spec["knowledge_base_ids"]),
                }
            )
        approval_checks = [
            (customer_approval, "customer approval"),
            (boundary_approval, "safety-boundary approval"),
        ]
        try:
            for approval, context in approval_checks:
                if approval:
                    verify_live_approval(owner, approval, f"post-key {context}")
        except (APIError, ImportFailure, KeyError, ValueError) as exc:
            affected_kb_ids = {
                str(approval.get("knowledge_base_id", ""))
                for approval, _ in approval_checks
                if approval
            }
            affected = [
                row
                for row in managed_keys
                if affected_kb_ids.intersection(row["knowledge_base_ids"])
            ]
            rollback_errors: List[str] = []
            for row in affected:
                try:
                    owner.request(
                        "DELETE",
                        f"/tenants/{tenant_id}/api-keys/{row['id']}",
                    )
                    secret_state["keys"].pop(row["key"], None)
                except (APIError, ImportFailure, OSError) as rollback_exc:
                    rollback_errors.append(f"{row['id']}: {rollback_exc}")
            try:
                write_secret_json(args.output, secret_state)
            except OSError as rollback_exc:
                rollback_errors.append(f"secret file: {rollback_exc}")
            if rollback_errors:
                raise ImportFailure(
                    "post-key FAQ snapshot drifted and fail-close key revocation was incomplete: "
                    + "; ".join(rollback_errors)
                ) from exc
            raise ImportFailure(
                "post-key FAQ snapshot drifted; every affected scoped key was revoked"
            ) from exc
        print(
            json.dumps(
                {
                    "status": "passed",
                    "secret_file": str(args.output.resolve()),
                    "keys": summaries,
                    "token_values_printed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (
        APIError,
        ImportFailure,
        BundleValidationError,
        FileNotFoundError,
        KeyError,
        OSError,
        ValueError,
    ) as exc:
        print(f"access-key setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
