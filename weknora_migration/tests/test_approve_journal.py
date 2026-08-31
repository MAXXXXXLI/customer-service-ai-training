#!/usr/bin/env python3
"""Focused fail-close and content-pinning tests for the FAQ publisher."""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock


MIGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MIGRATION_DIR))

from approve_faq import (  # noqa: E402
    apply_approval,
    json_content_sha256,
    load_approval_plan,
)
from import_bundle import ImportFailure  # noqa: E402


def faq_entry(enabled: bool = False) -> Dict[str, Any]:
    return {
        "standard_question": "test question",
        "similar_questions": ["test alias"],
        "negative_questions": [],
        "answers": ["test answer"],
        "answer_strategy": "all",
        "tag_name": "test",
        "is_enabled": enabled,
        "is_recommended": enabled,
    }


def remote_faq(enabled: bool = False) -> Dict[str, Any]:
    row = faq_entry(enabled)
    row.update(
        {
            "id": "100000001",
            "chunk_id": "chunk-1",
            "knowledge_base_id": "kb-customer",
        }
    )
    return row


class FakeClient:
    def __init__(self, events: List[str], failures: List[BaseException | None]) -> None:
        self.base_url = "http://127.0.0.1:18081"
        self.events = events
        self.failures = failures

    def request(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        self.events.append("remote-mutation")
        failure = self.failures.pop(0) if self.failures else None
        if failure is not None:
            raise failure
        return {"success": True, "data": {}}


class ApproveJournalTest(unittest.TestCase):
    def test_load_plan_unconditionally_rejects_publication_blocked_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="approve-plan-blocked-") as temp_dir:
            root = Path(temp_dir)
            faq_dir = root / "customer_approved"
            faq_dir.mkdir()
            entry = faq_entry()
            content_hash = json_content_sha256(entry)
            (faq_dir / "faq_entries.json").write_text(
                json.dumps([entry]),
                encoding="utf-8",
            )
            (faq_dir / "faq_metadata.jsonl").write_text(
                json.dumps(
                    {
                        "external_id": "FAQ-XLS-0002",
                        "standard_question": entry["standard_question"],
                        "risk_level": "高",
                        "secondary_review_required": True,
                        "publication_blocked": True,
                        "content_sha256": content_hash,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            approval_path = root / "approval.jsonl"
            (approval_path).write_text(
                json.dumps(
                    {
                        "external_id": "FAQ-XLS-0002",
                        "content_sha256": content_hash,
                        "decision": "approved",
                        "review_owner": "reviewer-a",
                        "secondary_review_owner": "reviewer-b",
                        "last_verified_at": "2026-08-26",
                        "effective_from": "2026-08-26",
                        "expires_on": "2026-12-31",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ImportFailure, "publication is blocked"):
                load_approval_plan(root, "customer", approval_path)

    def test_load_plan_rejects_metadata_hash_that_does_not_match_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="approve-plan-hash-") as temp_dir:
            root = Path(temp_dir)
            faq_dir = root / "customer_approved"
            faq_dir.mkdir()
            entry = faq_entry()
            (faq_dir / "faq_entries.json").write_text(
                json.dumps([entry]),
                encoding="utf-8",
            )
            wrong_hash = "0" * 64
            (faq_dir / "faq_metadata.jsonl").write_text(
                json.dumps(
                    {
                        "external_id": "FAQ-1",
                        "standard_question": entry["standard_question"],
                        "risk_level": "低",
                        "content_sha256": wrong_hash,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            approval_path = root / "approval.jsonl"
            approval_path.write_text(
                json.dumps(
                    {
                        "external_id": "FAQ-1",
                        "content_sha256": wrong_hash,
                        "decision": "pending",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ImportFailure, "actual FAQ payload"):
                load_approval_plan(root, "customer", approval_path)

    def publisher_fixture(self, temp: Path) -> tuple[Namespace, Dict[str, str], list, dict, list]:
        validation = {
            "bundle_version": "test-bundle",
            "bundle_manifest_sha256": "a" * 64,
        }
        entry = faq_entry()
        approvals = [
            {
                "external_id": "FAQ-1",
                "standard_question": entry["standard_question"],
                "content_sha256": json_content_sha256(entry),
                "decision": "approved",
            }
        ]
        desired = {entry["standard_question"]: True}
        args = Namespace(
            scope="customer",
            bundle=temp / "bundle-that-must-not-be-reread",
            import_receipt=temp / "runtime-receipt.json",
            base_url="http://127.0.0.1:18081",
            api_key="test-key",
            http_timeout=1.0,
            allow_version_mismatch=False,
            output=temp / "approval-receipt.json",
        )
        return args, validation, approvals, desired, [entry]

    def publisher_patches(
        self,
        client: FakeClient,
        list_side_effect: List[List[Dict[str, Any]]],
        writes: List[Dict[str, Any]],
        events: List[str],
    ) -> contextlib.AbstractContextManager[Any]:
        # ExitStack keeps this helper readable while making every external
        # dependency explicit.
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("approve_faq.read_json", return_value={
            "status": "passed",
            "tenant_partition": "runtime",
            "bundle_version": "test-bundle",
            "bundle_manifest_sha256": "a" * 64,
            "base_url": "http://127.0.0.1:18081",
            "tenant": {"id": "tenant-runtime"},
            "knowledge_bases": {"customer_approved": {"id": "kb-customer"}},
        }))
        stack.enter_context(mock.patch("approve_faq.WeKnoraClient", return_value=client))
        stack.enter_context(mock.patch("approve_faq.ensure_server_version", return_value={
            "version": "0.7.2"
        }))
        stack.enter_context(mock.patch("approve_faq.get_current_tenant", return_value={
            "id": "tenant-runtime",
            "name": "runtime",
        }))
        stack.enter_context(mock.patch(
            "approve_faq.list_all_faq_entries",
            side_effect=list_side_effect,
        ))
        stack.enter_context(mock.patch("approve_faq.envelope_data", return_value={}))

        def record_write(_path: Path, payload: Dict[str, Any]) -> None:
            writes.append(dict(payload))
            events.append(f"receipt-{payload['status']}")

        stack.enter_context(mock.patch("approve_faq.write_json_atomic", side_effect=record_write))
        return stack

    def test_keyboard_interrupt_fail_closes_then_rethrows_original(self) -> None:
        with tempfile.TemporaryDirectory(prefix="approve-interrupt-") as temp_dir:
            temp = Path(temp_dir)
            args, validation, approvals, desired, entries = self.publisher_fixture(temp)
            events: List[str] = []
            writes: List[Dict[str, Any]] = []
            client = FakeClient(events, [KeyboardInterrupt(), None])
            initial = remote_faq(False)
            disabled = remote_faq(False)
            with self.publisher_patches(
                client,
                [[initial], [initial], [disabled]],
                writes,
                events,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    apply_approval(args, validation, approvals, desired, entries)

            self.assertEqual(events[0], "receipt-applying")
            self.assertEqual(events.count("remote-mutation"), 2)
            self.assertEqual(writes[-1]["status"], "failed_fail_closed")
            self.assertTrue(writes[-1]["fail_close_verified"])

    def test_rollback_failure_still_writes_failed_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="approve-rollback-failure-") as temp_dir:
            temp = Path(temp_dir)
            args, validation, approvals, desired, entries = self.publisher_fixture(temp)
            events: List[str] = []
            writes: List[Dict[str, Any]] = []
            client = FakeClient(
                events,
                [OSError("primary write failed"), OSError("rollback write failed")],
            )
            initial = remote_faq(False)
            with self.publisher_patches(
                client,
                [[initial], [initial]],
                writes,
                events,
            ):
                with self.assertRaisesRegex(ImportFailure, "could not be verified fail-closed"):
                    apply_approval(args, validation, approvals, desired, entries)

            self.assertEqual(events[0], "receipt-applying")
            self.assertEqual(writes[-1]["status"], "failed_rollback_incomplete")
            self.assertFalse(writes[-1]["fail_close_verified"])
            self.assertIn("rollback write failed", writes[-1]["rollback_error"])

    def test_system_exit_fail_closes_then_preserves_exit_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="approve-system-exit-") as temp_dir:
            temp = Path(temp_dir)
            args, validation, approvals, desired, entries = self.publisher_fixture(temp)
            events: List[str] = []
            writes: List[Dict[str, Any]] = []
            client = FakeClient(events, [SystemExit(23), None])
            initial = remote_faq(False)
            with self.publisher_patches(
                client,
                [[initial], [initial], [remote_faq(False)]],
                writes,
                events,
            ):
                with self.assertRaises(SystemExit) as stopped:
                    apply_approval(args, validation, approvals, desired, entries)

            self.assertEqual(stopped.exception.code, 23)
            self.assertEqual(writes[-1]["status"], "failed_fail_closed")
            self.assertEqual(events[0], "receipt-applying")


if __name__ == "__main__":
    unittest.main()
