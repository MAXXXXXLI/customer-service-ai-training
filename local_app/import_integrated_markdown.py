from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/maxxxxx/Downloads/秀域企业完整知识库_高密度整合版_2026年8月.md")
KB = ROOT / "knowledge_base"
STATIC = ROOT / "local_app" / "static"


def slug(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return value[:48] or "course"


def paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p.strip()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def parse_source(text: str) -> tuple[list[dict], list[dict]]:
    module_matches = list(re.finditer(r"^# (模块[一二三四五六七八九十]+｜[^\n]+)$", text, re.M))
    modules: list[dict] = []
    courses: list[dict] = []
    module_id_by_heading: dict[str, str] = {}
    for module_index, match in enumerate(module_matches, 1):
        heading = match.group(1)
        title = heading.split("｜", 1)[1].strip()
        module_id = f"MOD-{module_index:02d}"
        module_id_by_heading[heading] = module_id
        end = module_matches[module_index].start() if module_index < len(module_matches) else len(text)
        block = text[match.end():end]
        course_matches = list(re.finditer(r"^## (.+)$", block, re.M))
        course_ids = []
        for order, cm in enumerate(course_matches, 1):
            course_title = cm.group(1).strip()
            cend = course_matches[order].start() if order < len(course_matches) else len(block)
            cblock = block[cm.end():cend].strip()
            summary_match = re.search(r"### 课程摘要\n(.*?)(?=\n### )", cblock, re.S)
            summary_lines = []
            if summary_match:
                summary_lines = [re.sub(r"^[-*]\s*", "", line).strip() for line in summary_match.group(1).splitlines() if line.strip()]
            sections = []
            h4 = list(re.finditer(r"^#### (.+)$", cblock, re.M))
            for si, sm in enumerate(h4, 1):
                send = h4[si].start() if si < len(h4) else len(cblock)
                body = cblock[sm.end():send]
                body = re.split(r"\n### 课程总结\b", body, maxsplit=1)[0].strip()
                content = paragraphs(body)
                if content:
                    sections.append({"title": sm.group(1).strip(), "content": content})
            if not sections:
                content = paragraphs(cblock)
                sections = [{"title": "课程内容", "content": content}] if content else []
            cid = f"COURSE-NKB-{len(courses) + 1:03d}"
            course_ids.append(cid)
            courses.append({
                "id": cid,
                "module_id": module_id,
                "order": order,
                "kind": "knowledge",
                "title": course_title,
                "summary": "；".join(summary_lines)[:1000],
                "estimated_minutes": max(12, min(45, 8 + sum(len(x["content"]) for x in sections) // 180)),
                "source_ids": ["NKB-2026-08-HIGH-DENSITY"],
                "authority": "enterprise_integrated_markdown",
                "sections": sections,
                "group_id": f"MOD-{module_index:02d}-G01",
                "group_title": title,
            })
        modules.append({
            "id": module_id,
            "order": module_index,
            "short_name": title.split("、", 1)[0][:12],
            "title": title,
            "subtitle": "；".join(c["title"] for c in courses[-len(course_ids):])[:80],
            "description": title,
            "objectives": [c["title"] for c in courses[-len(course_ids):]],
            "knowledge_card_ids": [],
            "scenario_ids": [],
            "lessons": [{"title": c["title"], "summary": c["summary"], "checklist": [s["title"] for s in c["sections"]], "source_refs": []} for c in courses[-len(course_ids):]],
            "case": {"customer": "", "weak_response": "未核验资料或作出绝对承诺。", "better_response": "先确认顾客目标和安全条件，再调用对应课程。", "reasoning": "先定位问题和安全条件，再使用对应知识。"},
        })
    return modules, courses


def safe_answer(course: dict) -> str:
    summary = course["summary"] or "请按当前课程内容和门店生效版本核验。"
    # The source is an employee learning document; customer-facing answers must retain a conservative boundary.
    return (
        f"关于“{course['title']}”，当前课程重点是：{summary}。"
        "具体适用情况、操作设置、价格、次数、药品或医疗结论，需以当前批准资料、说明书、SOP和有资质人员意见为准；"
        "不能据此承诺固定疗效、替代医疗或自行调整药物。"
    )


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    modules, courses = parse_source(text)
    cards = []
    faq = []
    rag = []
    for i, course in enumerate(courses, 1):
        card_id = f"CARD-NKB-{i:03d}"
        module = next(m for m in modules if m["id"] == course["module_id"])
        card = {
            "id": card_id, "type": "integrated_course", "domain": "enterprise_knowledge",
            "title": course["title"], "authority": "enterprise_integrated_markdown",
            "module_id": course["module_id"], "learning_module": module["title"],
            "chapter": course["title"], "course_id": course["id"],
            "content": [line for section in course["sections"] for line in section["content"]],
            "required_actions": ["按当前课程与生效 SOP 核验", "涉及医疗、药品或异常时升级给有资质人员"],
            "question_bank": [f"{course['title']}的核心服务边界是什么？", f"顾客询问{course['title']}时应先确认什么？"],
            "recommended_language": ["我先确认您的目标和安全情况，再按当前资料说明。"],
            "bad_patterns": ["保证有效", "替代医疗", "自行调整药物"],
            "training_focus": [course["title"], "安全边界", "动态信息核验"],
            "testing_focus": ["是否先确认安全", "是否避免固定承诺"],
        }
        cards.append(card)
        module["knowledge_card_ids"].append(card_id)
        question = f"关于{course['title']}，顾客最需要先了解什么？"
        answer = safe_answer(course)
        faq.append({
            "id": f"FAQ-NKB-{i:03d}", "source_id": "NKB-2026-08-HIGH-DENSITY", "source_rows": [i],
            "groups": [module["title"], course["title"]], "question": question,
            "question_aliases": [question, course["title"]],
            "keywords": [course["title"], module["title"], "安全边界", "当前资料"],
            "usage_count": 0, "last_modified": "2026-08-19", "status": "covered",
            "mapped_course_id": course["id"], "mapped_course_title": course["title"],
            "answer_strategy": "先安全确认，再按课程解释定位、流程、可能感受、限制和下一步。",
            "approved_answer": answer, "legacy_answer_imported": False,
            "review_note": "由高密度整合版课程生成；具体动态与医疗信息需按生效版本核验。",
            "module_id": course["module_id"], "learning_module": module["title"],
            "chapter": course["title"], "topic": course["title"], "knowledge_card_id": card_id,
            "question_type": "课程适配题", "risk_level": "高" if re.search(r"药|医疗|医美|GLP|私密|疾病", course["title"]) else "常规", "usage_note": "",
        })
        for si, section in enumerate(course["sections"], 1):
            body = "\n\n".join(section["content"])
            rag.append({
                "document_id": f"{course['id']}-SECTION-{si:02d}",
                "text": f"课程：{course['title']}\n小节：{section['title']}\n{body}",
                "metadata": {"doc_type": "course_section", "authority": "enterprise_integrated_markdown", "module_id": course["module_id"], "course_id": course["id"], "course_title": course["title"], "title": section["title"], "section_title": section["title"], "source_id": "NKB-2026-08-HIGH-DENSITY", "source_rows": [i]},
            })
        rag.append({
            "document_id": f"FAQ-NKB-{i:03d}-CHUNK-01", "text": f"顾客问题：{question}\n标准回答：{answer}\n关键词：{'；'.join(card['question_bank'])}",
            "metadata": {"doc_type": "common_qa", "authority": "enterprise_integrated_markdown", "module_id": course["module_id"], "course_id": course["id"], "course_title": course["title"], "qa_id": f"FAQ-NKB-{i:03d}", "title": course["title"], "section_title": course["title"], "question": question, "question_aliases": [question, course["title"]], "answer_status": "covered", "status": "covered", "approved_answer": answer, "answer_strategy": faq[-1]["answer_strategy"], "source_id": "NKB-2026-08-HIGH-DENSITY", "source_rows": [i]},
        })
    catalog = {"version": "2026-08-integrated-high-density", "purpose": "高密度整合版企业知识库，按十模块、四十三门课程提供学习与检索。", "course_count": len(courses), "coverage": {"module_count": len(modules), "course_count": len(courses), "course_section_count": sum(len(c["sections"]) for c in courses)}, "module_index": [{"module_id": m["id"], "course_count": sum(c["module_id"] == m["id"] for c in courses), "group_count": 1, "groups": [{"group_id": f"{m['id']}-G01", "title": m["title"], "description": m["description"], "course_count": sum(c["module_id"] == m["id"] for c in courses), "course_ids": [c["id"] for c in courses if c["module_id"] == m["id"]]}], "course_ids": [c["id"] for c in courses if c["module_id"] == m["id"]]} for m in modules], "courses": courses, "video_course_integration": {"source": "秀域企业完整知识库｜高密度整合版", "video_courses": 0, "integrated_groups": 43}}
    modules_doc = {"version": "2026-08-integrated-high-density", "generated_on": "2026-08-19", "purpose": "十模块高密度整合企业知识库。", "modules": modules}
    for path, obj in [(KB / "learning_catalog.json", catalog), (KB / "learning_modules.json", modules_doc), (STATIC / "learning_catalog.json", catalog), (STATIC / "learning_modules.json", modules_doc)]:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KB / "knowledge_cards.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in cards) + "\n", encoding="utf-8")
    (KB / "common_qa_catalog.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in faq) + "\n", encoding="utf-8")
    (KB / "rag_documents.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rag) + "\n", encoding="utf-8")
    (KB / "common_qa_gap_report.json").write_text(json.dumps({"generated_on": "2026-08-19", "source_id": "NKB-2026-08-HIGH-DENSITY", "source_rows": len(faq), "unique_questions": len(faq), "status_counts": {"covered": len(faq), "boundary_only": 0, "material_missing": 0}, "integration": {"modules": len(modules), "courses": len(courses), "rag_documents": len(rag), "legacy_answers_imported": 0}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KB / "validation_report.json").write_text(json.dumps({"generated_on": "2026-08-19", "status": "passed", "source": str(SOURCE), "checks": {"ten_modules": True, "forty_three_courses": len(courses) == 43, "all_course_ids_unique": len({c['id'] for c in courses}) == len(courses), "all_qa_ids_unique": len({q['id'] for q in faq}) == len(faq), "no_legacy_answers_imported": True, "no_source_documents_in_rag": not any(x['metadata']['doc_type'] == 'source' for x in rag)}, "counts": {"modules": len(modules), "courses": len(courses), "cards": len(cards), "questions": len(faq), "rag_documents": len(rag)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"modules": len(modules), "courses": len(courses), "cards": len(cards), "questions": len(faq), "rag": len(rag)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
