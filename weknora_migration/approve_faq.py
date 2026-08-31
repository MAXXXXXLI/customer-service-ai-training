#!/usr/bin/env python3
"""Publish only FAQ entries covered by a complete, content-pinned approval file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from import_bundle import (
    APIError,
    DEFAULT_BUNDLE,
    DEFAULT_RECEIPT_RUNTIME,
    ImportFailure,
    WeKnoraClient,
    assert_faq_entry_identity,
    ensure_server_version,
    envelope_data,
    get_current_tenant,
    list_all_faq_entries,
    read_json,
    read_jsonl,
    utc_now,
    write_json_atomic,
)
from verify_bundle import BundleValidationError, validate_bundle


MIGRATION_DIR = Path(__file__).resolve().parent
APPROVAL_TIMEZONE = timezone(timedelta(hours=8))
SCOPE_CONFIG = {
    "customer": {
        "bundle_key": "customer_approved",
        "kb_key": "customer_approved",
    },
    "safety-boundary": {
        "bundle_key": "safety_boundary",
        "kb_key": "safety_boundary",
    },
}


def faq_content(entry: Mapping[str, Any]) -> Dict[str, Any]:
    def string_list(field: str) -> List[str]:
        value = entry.get(field)
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
    }


def json_content_sha256(value: Any) -> str:
    """Hash JSON exactly as the bundle generator does."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def faq_by_question(
    entries: Sequence[Mapping[str, Any]],
    context: str,
) -> Dict[str, Mapping[str, Any]]:
    result: Dict[str, Mapping[str, Any]] = {}
    for row in entries:
        question = str(row.get("standard_question", "")).strip()
        if not question:
            raise ImportFailure(f"{context}: FAQ row has no standard_question")
        if question in result:
            raise ImportFailure(f"{context}: duplicate standard_question: {question}")
        result[question] = row
    return result


def faq_snapshot(entries: Sequence[Mapping[str, Any]], context: str) -> Dict[str, Any]:
    by_question = faq_by_question(entries, context)
    canonical = []
    enabled_entries = []
    for question, row in sorted(by_question.items()):
        item = {
            "standard_question": question,
            "id": str(row.get("id", "")),
            "chunk_id": str(row.get("chunk_id", "")),
            "knowledge_base_id": str(row.get("knowledge_base_id", "")),
            "content": faq_content(row),
            "is_enabled": bool(row.get("is_enabled")),
            "is_recommended": bool(row.get("is_recommended")),
        }
        canonical.append(item)
        if item["is_enabled"]:
            enabled_entries.append(
                {
                    "standard_question": question,
                    "chunk_id": item["chunk_id"],
                    "id": item["id"],
                }
            )
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "total": len(canonical),
        "enabled_count": len(enabled_entries),
        "disabled_count": len(canonical) - len(enabled_entries),
        "enabled_entries": enabled_entries,
    }


def parse_iso_date(value: Any, field: str, external_id: str) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ImportFailure(f"{external_id}: {field} must be YYYY-MM-DD") from exc


def load_approval_plan(
    bundle: Path,
    scope: str,
    approvals_path: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, bool]]:
    config = SCOPE_CONFIG[scope]
    bundle_key = config["bundle_key"]
    entries = read_json(bundle / bundle_key / "faq_entries.json")
    metadata = read_jsonl(bundle / bundle_key / "faq_metadata.jsonl")
    approvals = read_jsonl(approvals_path)
    if not isinstance(entries, list):
        raise ImportFailure("FAQ bundle payload is not a list")

    metadata_by_id = {str(row["external_id"]): row for row in metadata}
    entry_by_question = faq_by_question(entries, "verified bundle")
    approval_by_id: Dict[str, Dict[str, Any]] = {}
    for row in approvals:
        external_id = str(row.get("external_id", "")).strip()
        if not external_id:
            raise ImportFailure("approval row is missing external_id")
        if external_id in approval_by_id:
            raise ImportFailure(f"duplicate approval row: {external_id}")
        approval_by_id[external_id] = row
    if set(approval_by_id) != set(metadata_by_id):
        raise ImportFailure(
            "approval file must contain every current external_id exactly once; "
            f"missing={sorted(set(metadata_by_id) - set(approval_by_id))[:5]}, "
            f"extra={sorted(set(approval_by_id) - set(metadata_by_id))[:5]}"
        )

    today = datetime.now(APPROVAL_TIMEZONE).date()
    desired: Dict[str, bool] = {}
    normalized: List[Dict[str, Any]] = []
    for external_id, metadata_row in metadata_by_id.items():
        approval = approval_by_id[external_id]
        decision = str(approval.get("decision", "")).strip().lower()
        if decision not in {"approved", "rejected", "pending"}:
            raise ImportFailure(
                f"{external_id}: decision must be approved, rejected, or pending"
            )
        expected_hash = str(metadata_row.get("content_sha256", ""))
        question = str(metadata_row.get("standard_question", "")).strip()
        if question not in entry_by_question:
            raise ImportFailure(f"{external_id}: metadata question is absent from FAQ payload")
        actual_hash = json_content_sha256(entry_by_question[question])
        if expected_hash != actual_hash:
            raise ImportFailure(
                f"{external_id}: metadata content_sha256 does not match the actual FAQ payload"
            )
        if str(approval.get("content_sha256", "")) != actual_hash:
            raise ImportFailure(f"{external_id}: content_sha256 does not match the actual FAQ payload")

        enabled = decision == "approved"
        if enabled and metadata_row.get("publication_blocked") is True:
            raise ImportFailure(
                f"{external_id}: publication is blocked by bundle governance"
            )
        normalized_row = dict(approval)
        normalized_row["external_id"] = external_id
        normalized_row["standard_question"] = question
        normalized_row["decision"] = decision
        if enabled:
            owner = str(approval.get("review_owner", "")).strip()
            secondary = str(approval.get("secondary_review_owner", "")).strip()
            if not owner or owner.lower() == "unassigned":
                raise ImportFailure(f"{external_id}: approved entry requires review_owner")
            verified = parse_iso_date(approval.get("last_verified_at"), "last_verified_at", external_id)
            effective = parse_iso_date(approval.get("effective_from"), "effective_from", external_id)
            expires = parse_iso_date(approval.get("expires_on"), "expires_on", external_id)
            if verified > today:
                raise ImportFailure(f"{external_id}: last_verified_at cannot be in the future")
            if effective > today:
                raise ImportFailure(f"{external_id}: effective_from cannot be in the future")
            if effective > expires:
                raise ImportFailure(f"{external_id}: effective_from is after expires_on")
            if expires < today:
                raise ImportFailure(f"{external_id}: approval is already expired")
            needs_secondary = (
                scope == "safety-boundary"
                or metadata_row.get("risk_level") == "高"
                or metadata_row.get("secondary_review_required") is True
            )
            if needs_secondary and (
                not secondary
                or secondary.lower() == "unassigned"
                or secondary.casefold() == owner.casefold()
            ):
                raise ImportFailure(
                    f"{external_id}: independent secondary_review_owner is required"
                )
        desired[question] = enabled
        normalized.append(normalized_row)
    return entries, normalized, desired


def disable_all_faq_fail_closed(
    client: WeKnoraClient,
    kb_id: str,
    known_rows: Sequence[Mapping[str, Any]],
    context: str,
) -> None:
    try:
        current = list_all_faq_entries(client, kb_id)
    except (APIError, ImportFailure):
        current = list(known_rows)
    assert_faq_entry_identity(current, kb_id, f"{context} fail-close input")
    updates = {
        str(row["id"]): {"is_enabled": False, "is_recommended": False}
        for row in current
    }
    envelope_data(
        client.request(
            "PUT",
            f"/knowledge-bases/{kb_id}/faq/entries/fields",
            json_body={"by_id": updates, "exclude_ids": []},
        ),
        f"{context} fail-close disable",
    )
    reread = list_all_faq_entries(client, kb_id)
    assert_faq_entry_identity(reread, kb_id, f"{context} fail-close verification")
    if any(bool(row.get("is_enabled")) or bool(row.get("is_recommended")) for row in reread):
        raise ImportFailure(f"{context}: fail-close verification found an enabled FAQ")


def apply_approval(
    args: argparse.Namespace,
    validation: Mapping[str, Any],
    approvals: Sequence[Mapping[str, Any]],
    desired: Mapping[str, bool],
    verified_entries: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    api_key = args.api_key or os.environ.get("WEKNORA_API_KEY", "")
    if not api_key:
        raise ImportFailure("WEKNORA_API_KEY is required for --apply")
    receipt = read_json(args.import_receipt)
    if receipt.get("status") != "passed" or receipt.get("tenant_partition") != "runtime":
        raise ImportFailure("runtime import receipt is missing or not passed")
    if receipt.get("bundle_version") != validation["bundle_version"]:
        raise ImportFailure("runtime import receipt belongs to a different bundle")
    if receipt.get("bundle_manifest_sha256") != validation["bundle_manifest_sha256"]:
        raise ImportFailure("runtime import receipt belongs to different bundle content")

    client = WeKnoraClient(args.base_url, api_key, timeout=args.http_timeout)
    server = ensure_server_version(client, args.allow_version_mismatch)
    tenant = get_current_tenant(client)
    receipt_tenant = str(receipt.get("tenant", {}).get("id", ""))
    if tenant["id"] != receipt_tenant:
        raise ImportFailure("approval API key belongs to a different tenant")
    if str(receipt.get("base_url", "")).rstrip("/") != client.base_url:
        raise ImportFailure("runtime import receipt belongs to a different server")

    kb_key = SCOPE_CONFIG[args.scope]["kb_key"]
    kb = receipt.get("knowledge_bases", {}).get(kb_key, {})
    kb_id = str(kb.get("id", ""))
    if not kb_id:
        raise ImportFailure(f"runtime receipt has no KB ID for {kb_key}")
    # Use the exact in-memory entries whose hashes load_approval_plan verified.
    # Re-reading the bundle here would create a validation/use race.
    expected_by_question = faq_by_question(verified_entries, "verified bundle")
    approval_by_question = faq_by_question(approvals, "verified approval plan")
    if set(expected_by_question) != set(approval_by_question):
        raise ImportFailure("verified approval plan does not cover the exact FAQ payload")
    if set(expected_by_question) != set(desired):
        raise ImportFailure("desired FAQ flags do not cover the exact FAQ payload")
    for question, expected in expected_by_question.items():
        if str(approval_by_question[question].get("content_sha256", "")) != json_content_sha256(
            expected
        ):
            raise ImportFailure(
                f"verified FAQ content changed after approval-plan validation: {question}"
            )
    remote = list_all_faq_entries(client, kb_id)
    assert_faq_entry_identity(remote, kb_id, f"{args.scope} pre-approval")
    remote_by_question = faq_by_question(remote, f"{args.scope} pre-approval")
    if set(remote_by_question) != set(expected_by_question):
        raise ImportFailure("remote FAQ set differs from the verified bundle")
    for question, expected in expected_by_question.items():
        if faq_content(remote_by_question[question]) != faq_content(expected):
            raise ImportFailure(f"remote FAQ content drifted before approval: {question}")

    updates = {
        str(remote_by_question[question]["id"]): {
            "is_enabled": bool(enabled),
            "is_recommended": bool(enabled),
        }
        for question, enabled in desired.items()
    }

    # This atomic journal replaces any older passed receipt before the first
    # remote flag mutation. A crash can therefore never leave an old receipt
    # authorizing newly changed remote state.
    applying = {
        "status": "applying",
        "started_at": utc_now(),
        "scope": args.scope,
        "bundle_version": validation["bundle_version"],
        "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
        "base_url": client.base_url,
        "tenant": tenant,
        "knowledge_base_id": kb_id,
        "intended_enabled_count": sum(desired.values()),
        "intended_disabled_count": len(desired) - sum(desired.values()),
    }
    write_json_atomic(args.output, applying)

    try:
        envelope_data(
            client.request(
                "PUT",
                f"/knowledge-bases/{kb_id}/faq/entries/fields",
                json_body={"by_id": updates, "exclude_ids": []},
            ),
            f"apply {args.scope} FAQ approval",
        )
        reread = list_all_faq_entries(client, kb_id)
        assert_faq_entry_identity(reread, kb_id, f"{args.scope} post-approval")
        reread_by_question = faq_by_question(reread, f"{args.scope} post-approval")
        if set(reread_by_question) != set(expected_by_question):
            raise ImportFailure("remote FAQ set drifted while applying approval")
        for question, enabled in desired.items():
            row = reread_by_question.get(question)
            if row is None:
                raise ImportFailure(f"FAQ disappeared after approval: {question}")
            if faq_content(row) != faq_content(expected_by_question[question]):
                raise ImportFailure(f"remote FAQ content drifted while applying approval: {question}")
            if bool(row.get("is_enabled")) != enabled or bool(row.get("is_recommended")) != enabled:
                raise ImportFailure(f"FAQ flags differ after approval: {question}")

        snapshot = faq_snapshot(reread, f"{args.scope} approved snapshot")
        result = {
            "status": "passed",
            "completed_at": utc_now(),
            "scope": args.scope,
            "bundle_version": validation["bundle_version"],
            "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
            "base_url": client.base_url,
            "tenant": tenant,
            "knowledge_base_id": kb_id,
            "enabled_count": sum(desired.values()),
            "disabled_count": len(desired) - sum(desired.values()),
            "approvals": list(approvals),
            "faq_snapshot": snapshot,
            "server": server,
        }
        write_json_atomic(args.output, result)
        return result
    except BaseException as exc:
        rollback_exc: BaseException | None = None
        try:
            disable_all_faq_fail_closed(
                client,
                kb_id,
                remote,
                f"{args.scope} approval",
            )
        except BaseException as caught_rollback_exc:
            # Receipt writing is still attempted below. In particular, a
            # rollback failure must not leave the durable journal at merely
            # "applying" without recording that fail-close was incomplete.
            rollback_exc = caught_rollback_exc
        failure = {
            "status": (
                "failed_fail_closed"
                if rollback_exc is None
                else "failed_rollback_incomplete"
            ),
            "completed_at": utc_now(),
            "scope": args.scope,
            "bundle_version": validation["bundle_version"],
            "bundle_manifest_sha256": validation["bundle_manifest_sha256"],
            "base_url": client.base_url,
            "tenant": tenant,
            "knowledge_base_id": kb_id,
            "enabled_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "fail_close_verified": rollback_exc is None,
        }
        if rollback_exc is not None:
            failure["rollback_error"] = (
                f"{type(rollback_exc).__name__}: {rollback_exc}"
            )
        failure_receipt_exc: BaseException | None = None
        try:
            write_json_atomic(args.output, failure)
        except BaseException as caught_receipt_exc:
            failure_receipt_exc = caught_receipt_exc

        # KeyboardInterrupt, SystemExit, GeneratorExit, and any future direct
        # BaseException subclasses retain their original type and traceback.
        if not isinstance(exc, Exception):
            if rollback_exc is not None and hasattr(exc, "add_note"):
                exc.add_note(f"fail-close rollback failed: {rollback_exc}")
            if failure_receipt_exc is not None and hasattr(exc, "add_note"):
                exc.add_note(f"failed receipt could not be written: {failure_receipt_exc}")
            raise

        details = []
        if rollback_exc is not None:
            details.append(f"fail-close rollback failed: {rollback_exc}")
        if failure_receipt_exc is not None:
            details.append(f"failed receipt could not be written: {failure_receipt_exc}")
        suffix = f" ({'; '.join(details)})" if details else ""
        outcome = (
            "every FAQ in the target KB was disabled"
            if rollback_exc is None
            else "the target KB could not be verified fail-closed"
        )
        raise ImportFailure(
            f"{args.scope} approval failed; {outcome}{suffix}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=tuple(SCOPE_CONFIG), required=True)
    parser.add_argument("--approvals", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--import-receipt", type=Path, default=DEFAULT_RECEIPT_RUNTIME)
    parser.add_argument("--base-url", default=os.environ.get("WEKNORA_URL", "http://127.0.0.1:18081"))
    parser.add_argument("--api-key", default="", help="prefer WEKNORA_API_KEY")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-version-mismatch", action="store_true")
    parser.add_argument("--http-timeout", type=float, default=120.0)
    args = parser.parse_args()
    args.bundle = args.bundle.resolve()
    args.approvals = args.approvals.resolve()
    args.output = args.output or MIGRATION_DIR / f"approval_receipt.{args.scope}.json"
    try:
        validation = validate_bundle(args.bundle)
        verified_entries, approvals, desired = load_approval_plan(
            args.bundle,
            args.scope,
            args.approvals,
        )
        plan = {
            "status": "validated",
            "mode": "apply" if args.apply else "plan",
            "scope": args.scope,
            "bundle_version": validation["bundle_version"],
            "approved_count": sum(desired.values()),
            "disabled_count": len(desired) - sum(desired.values()),
        }
        if not args.apply:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        result = apply_approval(
            args,
            validation,
            approvals,
            desired,
            verified_entries,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
        print(f"approval failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
