from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
KB_ROOT = ROOT.parent / "knowledge_base"
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


catalog = json.loads((KB_ROOT / "learning_catalog.json").read_text(encoding="utf-8"))
static_catalog = json.loads((ROOT / "static" / "learning_catalog.json").read_text(encoding="utf-8"))
faq = read_jsonl(KB_ROOT / "common_qa_catalog.jsonl")
rag = read_jsonl(KB_ROOT / "rag_documents.jsonl")
registry = json.loads((KB_ROOT / "source_registry.json").read_text(encoding="utf-8"))

course_ids = {course["id"] for course in catalog["courses"]}
faq_course_ids = {
    "COURSE-FAQ-POINT-WAVE-001",
    "COURSE-FAQ-SUPER-V-001",
    "COURSE-FAQ-BEAUTY-001",
    "COURSE-FAQ-SLIMMING-001",
    "COURSE-FAQ-OBJECTION-001",
    "COURSE-FAQ-SAFETY-001",
}
faq_docs = [row for row in rag if row.get("metadata", {}).get("doc_type") == "common_qa"]
status_counts = Counter(row["status"] for row in faq)

checks: dict[str, bool] = {
    "source_rows_deduplicated": len(faq) == 1031,
    "all_questions_have_safe_answers": all(row.get("approved_answer") and row.get("answer_strategy") for row in faq),
    "legacy_answers_not_imported": all(row.get("legacy_answer_imported") is False for row in faq),
    "three_review_statuses_exist": status_counts == Counter({"boundary_only": 536, "material_missing": 390, "covered": 105}),
    "every_question_maps_to_course": all(row.get("mapped_course_id") in course_ids for row in faq),
    "six_learning_courses_added": faq_course_ids <= course_ids and catalog.get("course_count") == 44,
    "static_catalog_matches": catalog == static_catalog,
    "all_questions_are_retrievable_documents": len(faq_docs) == len(faq),
    "source_registered": any(source.get("source_id") == "SRC-035" for source in registry.get("sources", [])),
    "no_unreviewed_guarantees": not any(
        phrase in row["approved_answer"]
        for row in faq
        for phrase in ["保证有效", "肯定有效", "承诺永久不反弹", "可以治疗疾病", "可以替代医疗"]
    ),
}

retrieval_cases = {
    "点阵波打完更痛了怎么办": ("covered", "暂停"),
    "秀域184高纤饮应该怎么吃": ("material_missing", "缺少"),
    "Fotona 4D做完以后能正常吃饭喝水吗": ("material_missing", "医生"),
    "秀域定制内衣怎么洗": ("material_missing", "缺少"),
    "超V能治疗前列腺炎吗": ("boundary_only", "不能"),
}
retrieval_details = {}
for query, (expected_status, expected_text) in retrieval_cases.items():
    route = server.route_customer_question(query)
    docs = server.retrieve(query, limit=12, route=route)
    matches = [doc for doc in docs if doc.get("metadata", {}).get("doc_type") == "common_qa"]
    passed = any(
        doc.get("metadata", {}).get("answer_status") == expected_status
        and expected_text in doc.get("text", "")
        for doc in matches
    )
    checks[f"retrieve_{query}"] = passed
    retrieval_details[query] = [
        {
            "document_id": doc.get("document_id"),
            "status": doc.get("metadata", {}).get("answer_status"),
            "title": doc.get("metadata", {}).get("title"),
        }
        for doc in matches
    ]

report = {
    "status": "passed" if all(checks.values()) else "failed",
    "checks": checks,
    "details": {
        "questions": len(faq),
        "status_counts": dict(status_counts),
        "courses": len(catalog["courses"]),
        "rag_documents": len(rag),
        "retrieval": retrieval_details,
    },
}
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
