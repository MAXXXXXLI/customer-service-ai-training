#!/usr/bin/env python3
"""Verify the generated WeKnora bundle before any remote import.

The checks intentionally cover governance boundaries as well as file integrity:
the customer and safety FAQ sets must be exact, high-risk entries must remain
disabled, missing-material questions must stay out of runtime KBs, and every
audit snapshot hash must still match the bundled source copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence


MIGRATION_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MIGRATION_DIR.parent
KB_DIR = PROJECT_ROOT / "knowledge_base"
DEFAULT_BUNDLE = MIGRATION_DIR / "bundle"
MARKER = ".generated-by-build_bundle"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_app.import_integrated_markdown import parse_source as parse_integrated_source
from build_bundle import (
    BLOCKED_POINT_WAVE_EXTERNAL_ID,
    BLOCKED_POINT_WAVE_FAQ_ID,
    BUNDLE_VERSION,
)


class BundleValidationError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_safe_relative_path(root: Path, value: Any) -> bool:
    """Reject absolute paths, traversal, and symlinks escaping the bundle root."""

    relative = Path(str(value))
    if relative.is_absolute() or ".." in relative.parts:
        return False
    try:
        (root / relative).resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def all_faq_questions(entries: Sequence[Mapping[str, Any]]) -> List[str]:
    questions: List[str] = []
    for entry in entries:
        questions.append(str(entry["standard_question"]).strip())
        questions.extend(str(item).strip() for item in entry.get("similar_questions", []))
    return questions


def collect_sensitive_strings(
    value: Any,
    field_names: Sequence[str],
    minimum_length: int = 20,
) -> List[str]:
    wanted = set(field_names)
    results: List[str] = []

    def add_strings(item: Any) -> None:
        if isinstance(item, str):
            text = item.strip()
            if len(text) >= minimum_length:
                results.append(text)
        elif isinstance(item, list):
            for child in item:
                add_strings(child)
        elif isinstance(item, dict):
            for child in item.values():
                add_strings(child)

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in wanted:
                    add_strings(child)
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return list(dict.fromkeys(results))


def collect_all_strings(value: Any) -> List[str]:
    results: List[str] = []
    if isinstance(value, str):
        results.append(value)
    elif isinstance(value, list):
        for child in value:
            results.extend(collect_all_strings(child))
    elif isinstance(value, dict):
        for child in value.values():
            results.extend(collect_all_strings(child))
    return results


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class Validator:
    def __init__(self) -> None:
        self.checks = 0
        self.errors: List[str] = []

    def require(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def equal(self, actual: Any, expected: Any, message: str) -> None:
        self.require(actual == expected, f"{message}: expected={expected!r}, actual={actual!r}")

    def finish(self) -> None:
        if self.errors:
            formatted = "\n".join(f"- {item}" for item in self.errors)
            raise BundleValidationError(
                f"bundle verification failed with {len(self.errors)} error(s):\n{formatted}"
            )


def validate_document_manifest(
    validator: Validator,
    bundle: Path,
    kb_key: str,
) -> List[Dict[str, Any]]:
    manifest_path = bundle / kb_key / "document_manifest.jsonl"
    validator.require(manifest_path.is_file(), f"missing document manifest: {manifest_path}")
    if not manifest_path.is_file():
        return []
    rows = read_jsonl(manifest_path)
    ids: List[str] = []
    paths: List[str] = []
    for row in rows:
        relative = Path(row["path"])
        path = bundle / relative
        paths.append(row["path"])
        validator.require(
            is_safe_relative_path(bundle, relative),
            f"unsafe document path: {relative}",
        )
        validator.require(path.is_file(), f"missing document: {relative}")
        if path.is_file():
            validator.equal(sha256(path), row["sha256"], f"document hash mismatch: {relative}")
            validator.equal(path.stat().st_size, row["size_bytes"], f"document size mismatch: {relative}")
        metadata = row.get("metadata", {})
        validator.require(
            isinstance(metadata, dict) and all(isinstance(value, str) for value in metadata.values()),
            f"metadata must be map[string]string: {relative}",
        )
        document_id = metadata.get("document_id")
        validator.require(bool(document_id), f"missing document_id metadata: {relative}")
        if document_id:
            ids.append(document_id)
        validator.equal(
            metadata.get("customer_rag_allowed"),
            "false" if kb_key in {"staff_courses", "safety_policy", "audit_raw"} else "true",
            f"customer_rag_allowed boundary mismatch: {relative}",
        )
    validator.equal(len(ids), len(set(ids)), f"duplicate document_id in {kb_key}")
    validator.equal(len(paths), len(set(paths)), f"duplicate paths in {kb_key}")
    return rows


def compare_rebuild(bundle: Path, validator: Validator) -> None:
    with tempfile.TemporaryDirectory(prefix="weknora-bundle-verify-") as temp_dir:
        rebuilt = Path(temp_dir) / "bundle"
        command = [sys.executable, str(MIGRATION_DIR / "build_bundle.py"), "--output", str(rebuilt)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        validator.require(
            completed.returncode == 0,
            f"deterministic rebuild failed: {completed.stderr.strip() or completed.stdout.strip()}",
        )
        if completed.returncode != 0:
            return
        first = read_json(bundle / "bundle_manifest.json").get("files", [])
        second = read_json(rebuilt / "bundle_manifest.json").get("files", [])
        validator.equal(first, second, "rebuild output is not byte-for-byte deterministic")


def validate_bundle(bundle: Path, rebuild_check: bool = False) -> Dict[str, Any]:
    bundle = bundle.resolve()
    validator = Validator()
    validator.require(bundle.is_dir(), f"bundle directory not found: {bundle}")
    validator.require((bundle / MARKER).is_file(), f"generator marker missing: {MARKER}")
    validator.require((bundle / "bundle_manifest.json").is_file(), "bundle_manifest.json missing")
    if validator.errors:
        validator.finish()

    config = read_json(MIGRATION_DIR / "config.json")
    manifest = read_json(bundle / "bundle_manifest.json")
    validator.equal(manifest["bundle_version"], BUNDLE_VERSION, "bundle version")
    validator.equal(manifest["weknora"], config["weknora"], "WeKnora pin")
    validator.equal(
        (manifest["weknora"]["version"], manifest["weknora"]["commit"]),
        ("v0.7.2", "3d5d8bfcdfeeea266b292b71cea616847af28d0f"),
        "approved WeKnora release",
    )

    expected_kbs = {
        "staff_courses": ("KB-STAFF-COURSES", "document", "staff_only", "runtime"),
        "customer_approved": ("KB-CUSTOMER-PROVISIONAL", "faq", "reviewer_until_approved", "runtime"),
        "safety_policy": ("KB-SAFETY-POLICY", "document", "staff_only_until_reviewed", "runtime"),
        "safety_boundary": ("KB-SAFETY-BOUNDARY", "faq", "reviewer_until_approved", "runtime"),
        "audit_raw": ("KB-AUDIT-RAW", "document", "reviewer_admin_only", "audit"),
    }
    actual_kbs = {
        row["key"]: (
            row["name"],
            row["type"],
            row["access_policy"],
            row["tenant_group"],
        )
        for row in manifest["knowledge_bases"]
    }
    validator.equal(actual_kbs, expected_kbs, "five physical KB / two tenant layout")

    listed_files = {row["path"] for row in manifest["files"]}
    actual_files = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() and path.name not in {MARKER, "bundle_manifest.json"}
    }
    validator.equal(listed_files, actual_files, "bundle file inventory")
    for row in manifest["files"]:
        path = bundle / row["path"]
        validator.require(
            is_safe_relative_path(bundle, row["path"]),
            f"unsafe bundle path: {row['path']}",
        )
        validator.require(path.is_file(), f"manifest file missing: {row['path']}")
        if path.is_file():
            validator.equal(sha256(path), row["sha256"], f"bundle hash mismatch: {row['path']}")
            validator.equal(path.stat().st_size, row["size_bytes"], f"bundle size mismatch: {row['path']}")

    staff_manifest = validate_document_manifest(validator, bundle, "staff_courses")
    safety_manifest = validate_document_manifest(validator, bundle, "safety_policy")
    audit_manifest = validate_document_manifest(validator, bundle, "audit_raw")
    validator.equal(len(staff_manifest), 45, "staff document count")
    validator.equal(len(safety_manifest), 1, "safety policy document count")
    validator.equal(len(audit_manifest), manifest["counts"]["audit_documents"], "audit document count")
    if safety_manifest:
        safety_metadata = safety_manifest[0].get("metadata", {})
        validator.equal(
            safety_metadata.get("answer_status"),
            "staff_only_pending_named_review",
            "unreviewed safety policy answer status",
        )
        validator.equal(
            safety_metadata.get("review_owner"),
            "unassigned",
            "unreviewed safety policy owner",
        )

    learning_catalog = read_json(KB_DIR / "learning_catalog.json")
    learning_modules = read_json(KB_DIR / "learning_modules.json")
    cards = read_jsonl(KB_DIR / "knowledge_cards.jsonl")
    authoritative_name = "秀域企业完整知识库_高密度整合版_2026年8月.md"
    authority_path = KB_DIR / authoritative_name
    authority_lines = authority_path.read_text(encoding="utf-8").splitlines()
    parsed_modules, parsed_courses = parse_integrated_source(
        (KB_DIR / authoritative_name).read_text(encoding="utf-8")
    )
    parsed_module_by_id = {row["id"]: row for row in parsed_modules}
    for card in cards:
        parsed_module_by_id[card["module_id"]]["knowledge_card_ids"].append(card["id"])
    validator.equal(parsed_courses, learning_catalog["courses"], "authoritative Markdown -> course catalog")
    validator.equal(parsed_modules, learning_modules["modules"], "authoritative Markdown -> module catalog")
    validator.equal(len(learning_catalog["courses"]), 43, "current course count")
    validator.equal(len(cards), 43, "current knowledge card count")
    staff_ids = {row["metadata"]["document_id"] for row in staff_manifest}
    course_ids = {row["id"] for row in learning_catalog["courses"]}
    validator.equal(staff_ids & course_ids, course_ids, "all current courses emitted once")
    authority_starts = {}
    for course in learning_catalog["courses"]:
        heading = f"## {course['title']}"
        matches = [index for index, line in enumerate(authority_lines, 1) if line.strip() == heading]
        validator.equal(len(matches), 1, f"authority heading mapping: {course['id']}")
        if len(matches) == 1:
            authority_starts[course["id"]] = matches[0]
    authority_ranges = {
        course_id: {
            "line_start": start,
            "line_end": next(
                (
                    line_number
                    for line_number, line in enumerate(authority_lines[start:], start + 1)
                    if line.startswith("# ") or line.startswith("## ")
                ),
                len(authority_lines) + 1,
            )
            - 1,
        }
        for course_id, start in authority_starts.items()
    }
    for course in learning_catalog["courses"]:
        matches = [row for row in staff_manifest if row["metadata"]["document_id"] == course["id"]]
        validator.equal(len(matches), 1, f"course document mapping: {course['id']}")
        if len(matches) == 1:
            metadata = matches[0]["metadata"]
            expected_range = authority_ranges.get(course["id"], {})
            validator.equal(
                int(metadata.get("source_line_start", 0)),
                expected_range.get("line_start"),
                f"course source line start: {course['id']}",
            )
            validator.equal(
                int(metadata.get("source_line_end", 0)),
                expected_range.get("line_end"),
                f"course source line end: {course['id']}",
            )
            text = (bundle / matches[0]["path"]).read_text(encoding="utf-8")
            for section in course.get("sections", []):
                for paragraph in section.get("content", []):
                    validator.require(paragraph in text, f"course paragraph missing: {course['id']}")

    current_faq = read_jsonl(KB_DIR / "common_qa_catalog.jsonl")
    historical_faq = read_jsonl(KB_DIR / "common_qa_excel_catalog.jsonl")
    customer_entries = read_json(bundle / "customer_approved" / "faq_entries.json")
    customer_metadata = read_jsonl(bundle / "customer_approved" / "faq_metadata.jsonl")
    customer_approval_template = read_jsonl(
        bundle / "customer_approved" / "approval_template.jsonl"
    )
    boundary_entries = read_json(bundle / "safety_boundary" / "faq_entries.json")
    boundary_metadata = read_jsonl(bundle / "safety_boundary" / "faq_metadata.jsonl")
    boundary_approval_template = read_jsonl(
        bundle / "safety_boundary" / "approval_template.jsonl"
    )

    validator.equal(len(customer_entries), 49, "customer FAQ entry count")
    validator.equal(len(customer_metadata), 49, "customer FAQ metadata count")
    validator.equal(len(boundary_entries), 9, "safety boundary FAQ entry count")
    validator.equal(len(boundary_metadata), 9, "safety boundary metadata count")
    validator.equal(len(customer_approval_template), 49, "customer approval template count")
    validator.equal(len(boundary_approval_template), 9, "boundary approval template count")
    for entries, metadata_rows, label in (
        (customer_entries, customer_metadata, "customer"),
        (boundary_entries, boundary_metadata, "boundary"),
    ):
        entry_by_question = {row["standard_question"].strip(): row for row in entries}
        for metadata in metadata_rows:
            question = str(metadata.get("standard_question", "")).strip()
            validator.require(question in entry_by_question, f"{label} metadata has no FAQ: {question}")
            if question in entry_by_question:
                validator.equal(
                    metadata.get("content_sha256"),
                    json_sha256(entry_by_question[question]),
                    f"{label} FAQ content hash: {metadata.get('external_id')}",
                )
    for metadata_rows, template_rows, label in (
        (customer_metadata, customer_approval_template, "customer"),
        (boundary_metadata, boundary_approval_template, "boundary"),
    ):
        metadata_hashes = {
            row["external_id"]: row["content_sha256"] for row in metadata_rows
        }
        template_hashes = {
            row["external_id"]: row["content_sha256"] for row in template_rows
        }
        validator.equal(template_hashes, metadata_hashes, f"{label} approval content hashes")
        validator.require(
            all(row.get("decision") == "pending" for row in template_rows),
            f"{label} generated approval template must remain pending",
        )

    current_by_question = {row["question"].strip(): row for row in current_faq}
    emitted_by_question = {row["standard_question"].strip(): row for row in customer_entries}
    metadata_by_question = {row["standard_question"].strip(): row for row in customer_metadata}
    validator.equal(set(current_by_question), set(list(emitted_by_question)[:43]), "current FAQ ordering/mapping")
    for question, source in current_by_question.items():
        emitted = emitted_by_question.get(question)
        validator.require(emitted is not None, f"current FAQ missing: {source['id']}")
        if emitted is None:
            continue
        expected_enabled = False
        validator.equal(emitted["answers"], [source["approved_answer"].strip()], f"FAQ answer: {source['id']}")
        validator.equal(emitted["is_enabled"], expected_enabled, f"FAQ enabled state: {source['id']}")
        validator.equal(emitted["is_recommended"], expected_enabled, f"FAQ recommended state: {source['id']}")
        governance = metadata_by_question.get(question, {})
        course_id = str(source.get("mapped_course_id", ""))
        validator.equal(
            governance.get("source_record_indices"),
            source.get("source_rows", []),
            f"FAQ source record index: {source['id']}",
        )
        validator.require(
            "source_rows" not in governance,
            f"FAQ record index mislabeled as source rows: {source['id']}",
        )
        validator.equal(
            governance.get("source_line_start"),
            authority_ranges.get(course_id, {}).get("line_start"),
            f"FAQ source line start: {source['id']}",
        )
        validator.equal(
            governance.get("source_line_end"),
            authority_ranges.get(course_id, {}).get("line_end"),
            f"FAQ source line end: {source['id']}",
        )
    validator.equal(sum(bool(row["is_enabled"]) for row in customer_entries[:43]), 0, "enabled current FAQs")
    validator.equal(sum(not bool(row["is_enabled"]) for row in customer_entries[:43]), 43, "disabled provisional current FAQs")

    legacy_entries = [
        row
        for row in customer_entries
        if row.get("tag_name")
        in {"legacy-covered-review-required", "business-proposed-exception-blocked"}
    ]
    legacy_metadata = [
        row
        for row in customer_metadata
        if str(row.get("external_id", "")).startswith("FAQ-LEGACY-GROUP-")
        or row.get("external_id") == BLOCKED_POINT_WAVE_EXTERNAL_ID
    ]
    legacy_questions = set(all_faq_questions(legacy_entries))
    covered_questions = {
        str(question).strip()
        for row in historical_faq
        if row.get("status") == "covered"
        for question in [row["question"], *row.get("question_aliases", [])]
        if str(question).strip()
    }
    material_missing = {
        row["question"].strip() for row in historical_faq if row.get("status") == "material_missing"
    }
    boundary_questions = {
        row["question"].strip() for row in historical_faq if row.get("status") == "boundary_only"
    }
    validator.equal(len(legacy_entries), 6, "collapsed legacy covered answer groups")
    validator.equal(len(legacy_metadata), 6, "collapsed legacy covered metadata groups")
    validator.equal(legacy_questions, covered_questions, "covered historical question aliases")
    customer_question_forms = all_faq_questions(customer_entries)
    validator.equal(len(customer_question_forms), 196, "customer FAQ question-form count")
    validator.equal(len(set(customer_question_forms)), 196, "unique customer FAQ question forms")
    validator.require(
        all(not row["is_enabled"] and not row["is_recommended"] for row in legacy_entries),
        "legacy covered FAQ groups must remain disabled and non-recommended",
    )
    emitted_covered_map = {
        question: entry["answers"][0]
        for entry in legacy_entries
        for question in all_faq_questions([entry])
    }
    expected_covered_map = {
        str(question).strip(): row["approved_answer"].strip()
        for row in historical_faq
        if row.get("status") == "covered"
        for question in [row["question"], *row.get("question_aliases", [])]
        if str(question).strip()
    }
    validator.equal(emitted_covered_map, expected_covered_map, "covered question-to-answer mapping")
    legacy_metadata_by_question = {
        row["standard_question"].strip(): row for row in legacy_metadata
    }
    historical_by_question = {
        str(question).strip(): row
        for row in historical_faq
        for question in [row["question"], *row.get("question_aliases", [])]
        if str(question).strip()
    }
    for entry in legacy_entries:
        questions = all_faq_questions([entry])
        metadata = legacy_metadata_by_question.get(entry["standard_question"].strip(), {})
        source_rows = list(
            {
                historical_by_question[question]["id"]: historical_by_question[question]
                for question in questions
            }.values()
        )
        validator.equal(metadata.get("question_count"), len(questions), "covered metadata question count")
        validator.equal(
            metadata.get("original_question_ids"),
            [row["id"] for row in source_rows],
            "covered metadata question IDs",
        )
        validator.equal(
            metadata.get("source_rows"),
            sorted({n for row in source_rows for n in row.get("source_rows", [])}),
            "covered metadata source rows",
        )
        validator.equal(
            metadata.get("source_ids"),
            sorted({row.get("source_id") for row in source_rows if row.get("source_id")}),
            "covered metadata source IDs",
        )

    blocked_metadata_rows = [
        row for row in customer_metadata if row.get("external_id") == BLOCKED_POINT_WAVE_EXTERNAL_ID
    ]
    validator.equal(len(blocked_metadata_rows), 1, "blocked point-wave metadata identity")
    if len(blocked_metadata_rows) == 1:
        blocked_metadata = blocked_metadata_rows[0]
        blocked_question = str(blocked_metadata.get("standard_question", "")).strip()
        blocked_entry = emitted_by_question.get(blocked_question, {})
        source_row = next(
            (row for row in historical_faq if row.get("id") == BLOCKED_POINT_WAVE_FAQ_ID),
            {},
        )
        expected_aliases = [str(item).strip() for item in source_row.get("question_aliases", [])]
        validator.equal(blocked_question, "点阵波打完更痛了？", "blocked point-wave question")
        validator.equal(
            blocked_entry.get("similar_questions"),
            expected_aliases,
            "blocked point-wave aliases",
        )
        validator.equal(len(expected_aliases), 5, "blocked point-wave alias count")
        validator.equal(
            blocked_metadata.get("original_question_ids"),
            [BLOCKED_POINT_WAVE_FAQ_ID],
            "blocked point-wave source ID",
        )
        validator.equal(blocked_metadata.get("module_ids"), ["MOD-03"], "blocked point-wave module")
        validator.equal(blocked_metadata.get("risk_level"), "高", "blocked point-wave risk")
        validator.require(
            blocked_metadata.get("secondary_review_required") is True,
            "blocked point-wave FAQ must require independent secondary review",
        )
        validator.require(
            blocked_metadata.get("publication_blocked") is True,
            "blocked point-wave FAQ must remain publication-blocked",
        )
        validator.equal(
            blocked_metadata.get("authority_level"),
            "business_proposed_exception",
            "blocked point-wave authority level",
        )
        validator.require(
            blocked_entry.get("is_enabled") is False
            and blocked_entry.get("is_recommended") is False,
            "blocked point-wave FAQ must remain disabled and non-recommended",
        )

    emitted_boundary_questions = set(all_faq_questions(boundary_entries))
    validator.equal(emitted_boundary_questions, boundary_questions, "boundary-only question aliases")
    validator.equal(len(emitted_boundary_questions), 536, "boundary-only alias count")
    validator.require(
        all(not row["is_enabled"] and not row["is_recommended"] for row in boundary_entries),
        "unreviewed safety boundary FAQ groups must remain disabled and non-recommended",
    )
    validator.equal(
        {row["answers"][0] for row in boundary_entries},
        {row["approved_answer"].strip() for row in historical_faq if row.get("status") == "boundary_only"},
        "boundary-only answer set",
    )
    emitted_boundary_map = {
        question: entry["answers"][0]
        for entry in boundary_entries
        for question in all_faq_questions([entry])
    }
    expected_boundary_map = {
        row["question"].strip(): row["approved_answer"].strip()
        for row in historical_faq
        if row.get("status") == "boundary_only"
    }
    validator.equal(emitted_boundary_map, expected_boundary_map, "boundary question-to-answer mapping")
    boundary_metadata_by_question = {
        row["standard_question"].strip(): row for row in boundary_metadata
    }
    for entry in boundary_entries:
        questions = all_faq_questions([entry])
        metadata = boundary_metadata_by_question.get(entry["standard_question"].strip(), {})
        source_rows = [historical_by_question[question] for question in questions]
        validator.equal(metadata.get("question_count"), len(questions), "boundary metadata question count")
        validator.equal(
            metadata.get("original_question_ids"),
            sorted(row["id"] for row in source_rows),
            "boundary metadata question IDs",
        )
        validator.equal(
            metadata.get("source_rows"),
            sorted({n for row in source_rows for n in row.get("source_rows", [])}),
            "boundary metadata source rows",
        )
        validator.equal(
            metadata.get("source_ids"),
            sorted({row.get("source_id") for row in source_rows if row.get("source_id")}),
            "boundary metadata source IDs",
        )

    runtime_questions = set(all_faq_questions(customer_entries)) | emitted_boundary_questions
    validator.require(not (runtime_questions & material_missing), "material_missing leaked into runtime FAQ")
    validator.equal(len(material_missing), 390, "material_missing audit-only count")

    runtime_paths = [
        *(bundle / row["path"] for row in staff_manifest),
        *(bundle / row["path"] for row in safety_manifest),
        bundle / "customer_approved" / "faq_entries.json",
        bundle / "safety_boundary" / "faq_entries.json",
    ]
    runtime_text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_paths)
    runtime_logical_text = normalize_text(
        "\n".join(
            [
                *(path.read_text(encoding="utf-8") for path in runtime_paths[:-2]),
                *collect_all_strings(customer_entries),
                *collect_all_strings(boundary_entries),
            ]
        )
    )
    validator.require("直减800元" not in runtime_text, "expired 800-yuan promotion leaked into runtime KB")
    validator.require("周年庆感恩钜惠" not in runtime_text, "expired promotion wording leaked into runtime KB")

    video_review = read_jsonl(KB_DIR / "video_knowledge_review_queue.jsonl")
    validator.equal(len(video_review), 43, "video review queue count")
    validator.require(
        all(
            row.get("status") == "pending_review"
            and row.get("excluded_from_customer_rag") is True
            for row in video_review
        ),
        "video review queue contains an approved or customer-enabled item",
    )
    for row in video_review:
        validator.require(str(row["id"]) not in runtime_text, f"video review ID leaked: {row['id']}")
        issue = str(row.get("issue", "")).strip()
        if issue:
            validator.require(issue not in runtime_text, f"video review issue leaked: {row['id']}")
    for marker in ("VIDEO-REVIEW-", "CARD-VID-", "VIDEO-KNOWLEDGE-", "VID-G"):
        validator.require(marker not in runtime_text, f"video-only marker leaked into runtime KB: {marker}")

    real_exam = read_json(KB_DIR / "real_exam_bank.json")
    comprehensive_exam = read_json(KB_DIR / "comprehensive_exam_bank.json")
    scenario_rows = read_jsonl(KB_DIR / "scenario_library.jsonl")
    validator.require("REAL-EXAM-" not in runtime_text, "real exam IDs leaked into runtime KB")
    validator.require("SCN-CEX-" not in runtime_text, "scenario IDs leaked into runtime KB")
    validator.require("hidden_information" not in runtime_text, "scenario hidden fields leaked into runtime KB")
    validator.require("reference_answer" not in runtime_text, "scenario reference answers leaked into runtime KB")
    for filename in (
        "real_exam_bank.json",
        "comprehensive_exam_bank.json",
        "scenario_library.jsonl",
        "video_knowledge_review_queue.jsonl",
    ):
        validator.require(filename not in runtime_text, f"audit-only source filename leaked: {filename}")
    validator.equal(len(real_exam.get("exams", [])), 4, "real exam set count")
    validator.equal(len(scenario_rows), 30, "scenario library count")
    validator.equal(
        sum(len(module.get("fill_blanks", [])) for module in comprehensive_exam.get("modules", [])),
        60,
        "comprehensive fill-blank count",
    )
    validator.equal(
        sum(len(module.get("choices", [])) for module in comprehensive_exam.get("modules", [])),
        80,
        "comprehensive choice count",
    )
    validator.equal(
        sum(len(module.get("scenarios", [])) for module in comprehensive_exam.get("modules", [])),
        30,
        "comprehensive scenario count",
    )
    exam_sensitive_fields = (
        "prompt",
        "reference_answer",
        "explanation",
        "score_note",
        "answer_parts",
        "hidden_information",
        "information_release_rules",
        "must_test",
        "critical_failures",
    )
    for label, source in (
        ("real exam", real_exam),
        ("comprehensive exam", comprehensive_exam),
    ):
        for text in collect_sensitive_strings(source, exam_sensitive_fields):
            normalized = normalize_text(text)
            validator.require(
                normalized not in runtime_logical_text,
                f"{label} hidden content leaked: {normalized[:60]}",
            )
    for scenario in scenario_rows:
        reference_answer = str(scenario.get("reference_answer", "")).strip()
        if reference_answer:
            validator.require(
                normalize_text(reference_answer) not in runtime_logical_text,
                f"scenario reference answer leaked: {scenario['id']}",
            )

    taxonomy = read_json(bundle / "taxonomy.json")
    validator.equal(
        taxonomy["counts"],
        {"systems": 2, "modules": 10, "courses": 43, "leaf_titles": 424},
        "taxonomy counts",
    )

    snapshot_manifest = read_json(bundle / "source_snapshot_manifest.json")
    validator.equal(
        len(snapshot_manifest),
        manifest["counts"]["source_snapshot_files_total"],
        "snapshot inventory count",
    )
    for row in snapshot_manifest:
        relative = Path(row["path"])
        path = bundle / relative
        validator.require(
            is_safe_relative_path(bundle, relative),
            f"unsafe snapshot path: {relative}",
        )
        source_label = str(row.get("source_path", ""))
        source_base = source_label.split("!", 1)[0]
        source_relative = Path(source_base)
        validator.require(
            bool(source_label)
            and not source_relative.is_absolute()
            and ".." not in source_relative.parts
            and source_relative.parts[:1] in {("project",), ("source_inputs",)},
            f"non-portable snapshot source_path: {source_label!r}",
        )
        validator.require(path.is_file(), f"snapshot file missing: {relative}")
        if path.is_file():
            validator.equal(sha256(path), row["sha256"], f"snapshot hash mismatch: {relative}")
            validator.equal(path.stat().st_size, row["size_bytes"], f"snapshot size mismatch: {relative}")
    origin_counts: Dict[str, int] = {}
    for row in snapshot_manifest:
        origin = str(row.get("origin", ""))
        origin_counts[origin] = origin_counts.get(origin, 0) + 1
    expected_origins = {
        "2026-08-15-handoff-archive": 36,
        "current_original": 1,
        "current_workspace": 33,
        "workspace_taxonomy": 2,
    }
    validator.equal(origin_counts, expected_origins, "snapshot origin counts")
    validator.equal(
        manifest["counts"].get("source_snapshot_origin_counts"),
        expected_origins,
        "manifest snapshot origin counts",
    )
    original_rows = [row for row in snapshot_manifest if row.get("origin") == "current_original"]
    validator.equal(len(original_rows), 1, "registered original snapshot count")
    if len(original_rows) == 1:
        original = original_rows[0]
        validator.equal(
            original.get("path"),
            "source_snapshot/originals/SRC-035-1786691706191.xls",
            "SRC-035 snapshot path",
        )
        validator.equal(original.get("size_bytes"), 535552, "SRC-035 snapshot size")
        validator.equal(
            original.get("sha256"),
            "7bbf62447a6857b5968c238418fac12435c1697c4a13f2b6acc78c218984ce44",
            "SRC-035 snapshot SHA-256",
        )

    source_copy = bundle / "source_snapshot" / "knowledge_base" / authoritative_name
    validator.require(source_copy.is_file(), "authoritative course source missing from snapshot")
    if source_copy.is_file():
        validator.equal(sha256(source_copy), sha256(KB_DIR / authoritative_name), "authoritative source snapshot")
    validator.require(
        manifest["authority"].get("current_source_registry_gap_recorded") is True,
        "source-registry gap not recorded",
    )
    extension_path = bundle / "source_registry_extension.json"
    validator.require(extension_path.is_file(), "source registry extension missing")
    if extension_path.is_file():
        extension = read_json(extension_path)
        validator.equal(extension.get("source_id"), "NKB-2026-08-HIGH-DENSITY", "authority source ID")
        validator.equal(extension.get("sha256"), sha256(authority_path), "authority registry SHA-256")
        validator.equal(
            extension.get("relative_path"),
            f"knowledge_base/{authoritative_name}",
            "authority registry path",
        )
        validator.equal(
            manifest["authority"].get("authority_sha256"),
            extension.get("sha256"),
            "manifest authority SHA-256",
        )
    original_registry = read_json(KB_DIR / "source_registry.json")
    original_source_ids = {
        str(row.get("source_id"))
        for row in original_registry.get("sources", [])
        if row.get("source_id")
    }
    validator.require(
        "NKB-2026-08-HIGH-DENSITY" not in original_source_ids,
        "expected source-registry gap no longer exists; remove the extension workflow",
    )

    counts = manifest["counts"]
    expected_counts = {
        "modules": 10,
        "courses": 43,
        "course_sections": 129,
        "course_paragraphs": 931,
        "knowledge_cards": 43,
        "card_training_questions": 86,
        "current_faq": 43,
        "current_faq_enabled": 0,
        "current_faq_provisional_disabled": 38,
        "current_faq_high_risk_disabled": 5,
        "historical_faq": 1031,
        "historical_faq_status": {
            "boundary_only": 536,
            "covered": 105,
            "material_missing": 390,
        },
        "historical_covered_collapsed_entries": 6,
        "customer_faq_payload_entries": 49,
        "safety_boundary_answer_groups": 9,
        "safety_boundary_question_aliases": 536,
        "safety_boundary_enabled": 0,
        "safety_boundary_provisional_disabled": 9,
        "video_review_items": 43,
        "video_review_risks": {
            "专业复核": 20,
            "动态核验": 2,
            "常规": 2,
            "设备复核": 6,
            "高风险复核": 13,
        },
        "staff_documents": 45,
        "safety_documents": 1,
        "safety_boundary_faq_entries": 9,
        "audit_documents": 73,
        "registered_sources_original": 35,
        "registered_sources_effective": 36,
        "source_snapshot_files_total": 72,
        "historical_raw_file_count": 36,
        "historical_unique_source_ids": 34,
    }
    for key, value in expected_counts.items():
        validator.equal(counts.get(key), value, f"bundle count {key}")

    if rebuild_check:
        compare_rebuild(bundle, validator)

    validator.finish()
    return {
        "status": "passed",
        "bundle": str(bundle),
        "checks": validator.checks,
        "bundle_version": manifest["bundle_version"],
        "bundle_manifest_sha256": sha256(bundle / "bundle_manifest.json"),
        "weknora": manifest["weknora"],
        "knowledge_bases": [row["name"] for row in manifest["knowledge_bases"]],
        "counts": counts,
        "rebuild_check": rebuild_check,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument(
        "--rebuild-check",
        action="store_true",
        help="regenerate into a temporary directory and compare every output hash",
    )
    args = parser.parse_args()
    try:
        report = validate_bundle(args.bundle, rebuild_check=args.rebuild_check)
    except (BundleValidationError, FileNotFoundError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
