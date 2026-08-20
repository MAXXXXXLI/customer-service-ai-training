from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "knowledge_base" / "real_exam_bank.json"
STATIC = ROOT / "local_app" / "static" / "data" / "real_exam_bank.json"
HTML = (ROOT / "local_app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "local_app" / "static" / "app.js").read_text(encoding="utf-8")


def main() -> None:
    bank = json.loads(CANONICAL.read_text(encoding="utf-8"))
    static = json.loads(STATIC.read_text(encoding="utf-8"))
    assert static == bank

    exams = bank["exams"]
    expected_ids = [
        "REAL-EXAM-NEW-EMPLOYEE-2026",
        "REAL-EXAM-STORE-EMPLOYEE-01",
        "REAL-EXAM-STORE-EMPLOYEE-02",
        "REAL-EXAM-SLIMMING-SUBSIDY-2026-08-B",
    ]
    assert [exam["id"] for exam in exams] == expected_ids
    assert [exam["order"] for exam in exams] == [1, 2, 3, 4]
    assert [exam["source_file"] for exam in exams] == [
        "2026新员工考试题.docx",
        "新员工下店考试题1.docx",
        "新员工下店考试题2.docx",
        "UMU_2026年8月减肥技能津贴考试（下）.xlsx",
    ]
    assert [exam["source_sha256"] for exam in exams] == [
        "61d59d12b4733200fcde0095fa2fcf3a7edc8d82774e4525da3432d672b00454",
        "cef228ed8c598fc3b692d9850e7ea10f6cb53ebee1c10752e92b1a4f43316b4d",
        "888ec2af0125c7804f4ba432a380c9e5f548fab23cee6f45e9ba70becd1a7b31",
        "251bce1fded076db30a9e58faa3bd88329f83c4786ee7c6a3e18eb460fe208cb",
    ]
    assert hashlib.sha256(CANONICAL.read_bytes()).digest() == hashlib.sha256(STATIC.read_bytes()).digest()
    assert [len(exam["questions"]) for exam in exams] == [12, 12, 11, 16]
    assert all(sum(float(question["points"]) for question in exam["questions"]) == float(exam["total_points"]) == 100 for exam in exams)
    assert sum(len(exam["questions"]) for exam in exams) == 51
    assert all(not Path(exam["source_file"]).is_absolute() for exam in exams)
    assert all(exam["score_note"] for exam in exams)
    assert not set(expected_ids) & {f"MOD-{index:02d}" for index in range(1, 11)}

    all_question_ids: list[str] = []
    for exam in exams:
        questions = exam["questions"]
        assert len({question["id"] for question in questions}) == len(questions)
        assert all(question["type"] in {"fill_blank", "short_answer"} for question in questions)
        assert all(question["prompt"] and question["reference_answer"] for question in questions)
        assert all(float(question["points"]) > 0 for question in questions)
        all_question_ids.extend(question["id"] for question in questions)
        for question in questions:
            if question["type"] != "fill_blank":
                continue
            blanks = re.findall(r"_{4,}", question["prompt"])
            parts = question["answer_parts"]
            assert len(blanks) == len(parts), (exam["id"], question["id"], len(blanks), len(parts))
            assert all(part["answer"] for part in parts)
    assert len(all_question_ids) == len(set(all_question_ids))
    unordered_ids = {
        question["id"]
        for exam in exams
        for question in exam["questions"]
        if question.get("order_sensitive") is False
    }
    assert unordered_ids == {"NESE1-F04", "NESE2-F02"}

    assert 'class="conversation-stage hidden" id="conversation-stage"' in HTML
    for marker in [
        'fetch(staticAsset("data/real_exam_bank.json"))',
        'function routeItemById(',
        'function examQuestions(',
        'class="module-route-group real-exam-group"',
        'data-manual-score=',
        'function finalizeObjectiveReview(',
        'const numericLike =',
        'if (question.order_sensitive === false)',
        'class="answer-explanation"',
    ]:
        assert marker in JS, marker

    print(json.dumps({
        "status": "passed",
        "real_exams": len(exams),
        "question_counts": [len(exam["questions"]) for exam in exams],
        "total_questions": 51,
        "total_points_each": 100,
        "initial_conversation_hidden": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
