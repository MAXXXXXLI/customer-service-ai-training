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
faq_docs = [row for row in rag if row.get("metadata", {}).get("doc_type") == "common_qa"]
status_counts = Counter(row["status"] for row in faq)

checks: dict[str, bool] = {
    "source_rows_deduplicated": len(faq) == 43 and len({row.get("id") for row in faq}) == len(faq),
    "all_questions_have_safe_answers": all(row.get("approved_answer") and row.get("answer_strategy") for row in faq),
    "legacy_answers_not_imported": all(row.get("legacy_answer_imported") is False for row in faq),
    "new_catalog_questions_are_covered": status_counts == Counter({"covered": 43}),
    "every_question_maps_to_course": all(row.get("mapped_course_id") in course_ids for row in faq),
    "integrated_learning_courses_loaded": catalog.get("course_count") == len(catalog.get("courses", [])) and len(catalog.get("courses", [])) == 43,
    "static_catalog_matches": catalog == static_catalog,
    "all_questions_are_retrievable_documents": len(faq_docs) == len(faq),
    "source_registered": any(source.get("source_id") == "SRC-035" for source in registry.get("sources", [])),
    "no_unreviewed_guarantees": all(
        ("不能据此承诺" in row["approved_answer"] or "不能承诺" in row["approved_answer"])
        for row in faq
    ),
}

retrieval_cases = {
    "点阵波服务后反应与异常处理": ("covered", "不能据此承诺"),
    "184饱腹产品：定位、使用与注意事项": ("covered", "不能据此承诺"),
    "松弛、热玛吉、线雕与Fotona 4D": ("covered", "不能据此承诺"),
    "定制内衣：洗护、修改、售后与价格异议": ("covered", "不能据此承诺"),
    "关节、运动损伤与高风险疾病分流": ("covered", "不能据此承诺"),
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
