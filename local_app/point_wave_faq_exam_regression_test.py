from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = ROOT / "knowledge_base" / "point_wave_faq_exam.json"
STATIC_PATH = ROOT / "local_app" / "static" / "data" / "point_wave_faq_exam.json"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalized(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).lower()


def main() -> None:
    bank = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    static_bank = json.loads(STATIC_PATH.read_text(encoding="utf-8"))
    assert static_bank == bank, "static point-wave FAQ exam must mirror the canonical file"

    comprehensive = json.loads(
        (ROOT / "knowledge_base" / "comprehensive_exam_bank.json").read_text(encoding="utf-8")
    )
    module = next(item for item in comprehensive["modules"] if item["id"] == "MOD-03")
    assert bank["schema_version"] == "1.0"
    assert bank["module_id"] == module["id"] == "MOD-03"
    assert bank["module_title"] == module["title"] == "点阵波与疼痛服务"
    assert bank["title"] == "点阵波 FAQ 关键词问答"
    assert bank["scoring"]["method"] == "keyword_group_threshold"

    current_faq = {
        item["id"]: item
        for item in [
            *load_jsonl(ROOT / "knowledge_base" / "common_qa_catalog.jsonl"),
            *load_jsonl(ROOT / "knowledge_base" / "common_qa_excel_catalog.jsonl"),
        ]
    }
    questions = bank["questions"]
    assert len(questions) == 8
    question_ids = [item["id"] for item in questions]
    assert len(question_ids) == len(set(question_ids))
    assert question_ids == [f"FAQ-M03-K{index:02d}" for index in range(1, 9)]

    all_group_ids: list[str] = []
    all_sources: set[str] = set()
    for question in questions:
        assert question["module_id"] == "MOD-03"
        assert "点阵波" in question["prompt"]
        assert question["points"] == 10
        assert question["reference_answer"].strip()
        assert len(question["source_faq_ids"]) >= 2
        assert any(source_id.startswith("FAQ-XLS-") for source_id in question["source_faq_ids"])
        assert any(source_id.startswith("FAQ-NKB-") for source_id in question["source_faq_ids"])
        for source_id in question["source_faq_ids"]:
            assert source_id in current_faq, f"missing current FAQ source: {source_id}"
            assert current_faq[source_id]["status"] in {"covered", "boundary_only"}
            all_sources.add(source_id)

        groups = question["keyword_groups"]
        assert len(groups) >= 5
        assert 1 <= question["minimum_groups"] <= len(groups)
        labels = [group["label"] for group in groups]
        assert len(labels) == len(set(labels))
        for group in groups:
            assert group["id"].startswith(f'{question["id"]}-G')
            all_group_ids.append(group["id"])
            assert group["label"].strip()
            assert len(group["terms"]) >= 3
            terms = [normalized(term) for term in group["terms"]]
            assert all(terms)
            assert len(terms) == len(set(terms)), f'duplicate synonym in {group["id"]}'
            assert any(len(term) <= 8 for term in terms), f'missing short natural synonym in {group["id"]}'

    assert len(all_group_ids) == len(set(all_group_ids))
    assert len(all_sources) >= 20

    required_groups = {
        question["id"]: {group["id"] for group in question["keyword_groups"] if group.get("required")}
        for question in questions
    }
    assert {"FAQ-M03-K02-G01", "FAQ-M03-K02-G02"} <= required_groups["FAQ-M03-K02"]
    assert {"FAQ-M03-K03-G05", "FAQ-M03-K03-G06"} <= required_groups["FAQ-M03-K03"]
    assert {"FAQ-M03-K06-G05", "FAQ-M03-K06-G06"} <= required_groups["FAQ-M03-K06"]
    assert {"FAQ-M03-K07-G03", "FAQ-M03-K07-G04"} <= required_groups["FAQ-M03-K07"]

    serialized = json.dumps(bank, ensure_ascii=False)
    forbidden_legacy_claims = [
        "微损伤",
        "痛则不通",
        "第二天消失",
        "越痛越有效",
        "越疼越有效",
        "忍几分钟",
        "量变才能引得质变",
    ]
    assert not [claim for claim in forbidden_legacy_claims if claim in serialized]

    print(
        json.dumps(
            {
                "status": "passed",
                "module_id": bank["module_id"],
                "questions": len(questions),
                "keyword_groups": len(all_group_ids),
                "required_groups": sum(len(groups) for groups in required_groups.values()),
                "faq_sources": len(all_sources),
                "static_mirror": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
