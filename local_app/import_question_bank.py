from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/maxxxxx/Downloads/秀域企业完整知识库_模块培训与测试题库_30题_2026年8月.md")
OUTPUT = ROOT / "knowledge_base" / "scenario_library.jsonl"
STATIC_OUTPUT = ROOT / "local_app" / "static" / "data" / "scenario_library.jsonl"

MODULES = [
    ("MOD-01", "enterprise_service", "企业治理与服务标准"),
    ("MOD-02", "customer_service", "顾客沟通与服务闭环"),
    ("MOD-03", "point_wave", "点阵波与疼痛服务"),
    ("MOD-04", "super_v", "超V热动力与亚健康服务"),
    ("MOD-05", "weight_management", "科学减重与营养管理"),
    ("MOD-06", "glp1_medical", "GLP-1与医疗减重项目"),
    ("MOD-07", "body_management", "184、轰脂塑形与定制内衣"),
    ("MOD-08", "skin_hair", "皮肤管理、设备操作与毛囊养护"),
    ("MOD-09", "spring_face_medical_beauty", "春语面部年轻化与医美"),
    ("MOD-10", "private_health", "春语私密健康"),
]


def clean(value: str) -> str:
    value = re.sub(r"\*+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse() -> list[dict]:
    text = SOURCE.read_text(encoding="utf-8")
    first, answers = text.split("# 第二部分｜标准答案与评分要点", 1)
    modules = re.split(r"(?m)^## 模块", first)[1:]
    answer_modules = re.split(r"(?m)^## 模块", answers)[1:]
    answer_map: dict[tuple[int, int], tuple[str, list[str]]] = {}
    for mi, block in enumerate(answer_modules, 1):
        for match in re.finditer(r"(?ms)^### 答案(\d+)｜.*?\n\n\*\*标准答案：\*\*\n(.*?)(?=\n\n### 答案|\n\n## |\Z)", block):
            qi = int(match.group(1))
            answer = clean(match.group(2).split("**评分要点：**", 1)[0])
            points_match = re.search(r"\*\*评分要点：\*\*\n(.*?)(?=\n\n### 答案|\n\n## |\Z)", block[match.start():], re.S)
            points = []
            if points_match:
                points = [clean(re.sub(r"^\s*-\s*", "", line)) for line in points_match.group(1).splitlines() if re.match(r"\s*-", line)]
            answer_map[(mi, qi)] = (answer, points[:4])

    rows = []
    persona_defaults = [
        (34, "女", "企业职员", "谨慎、会追问"),
        (41, "女", "个体经营者", "关注安全和预算"),
        (36, "女", "教师", "重视隐私、希望听懂"),
    ]
    for mi, block in enumerate(modules, 1):
        module_id, domain, module_title = MODULES[mi - 1]
        questions = re.findall(r"(?m)^### 问题(\d+)｜(.+)$", block)
        for qi_text, question in questions:
            qi = int(qi_text)
            answer, points = answer_map.get((mi, qi), ("", []))
            age, gender, occupation, style = persona_defaults[(qi - 1) % len(persona_defaults)]
            lower = question.lower()
            objections = []
            for key, label in [
                ("价格", "预算和价格"), ("贵", "担心价格"), ("疼", "担心疼痛"),
                ("效果", "担心效果"), ("反弹", "担心反弹"), ("隐私", "担心隐私"),
                ("副作用", "担心不适"), ("停", "想知道后续安排"), ("一次就", "想一次解决"),
                ("剂量", "想要具体用法"), ("医院", "不想被转诊"), ("永久", "期待永久效果"),
            ]:
                if key in lower and label not in objections:
                    objections.append(label)
            if not objections:
                objections = ["怕被推销", "希望先听懂再决定"]
            rows.append({
                "id": f"SCN-QBANK-M{mi:02d}-Q{qi:02d}",
                "module_id": module_id,
                "module_title": module_title,
                "question_id": f"M{mi:02d}-Q{qi:02d}",
                "domain": domain,
                "persona": {"age": age, "gender": gender, "occupation": occupation, "style": style, "goal": module_title, "knowledge_level": "按题目扮演普通顾客"},
                "opening": clean(question),
                "question": clean(question),
                "hidden_objections": objections[:3],
                "must_test": points or ["直接回答题目并说明必要边界", "给出可执行的下一步"],
                "reference_answer": answer,
                "scoring_points": points,
                "source": SOURCE.name,
            })
    if len(rows) != 30:
        raise RuntimeError(f"expected 30 questions, got {len(rows)}")
    return rows


def main() -> None:
    rows = parse()
    payload = "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n"
    OUTPUT.write_text(payload, encoding="utf-8")
    STATIC_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    STATIC_OUTPUT.write_text(payload, encoding="utf-8")
    print(json.dumps({"questions": len(rows), "modules": len(set(row["module_id"] for row in rows)), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
