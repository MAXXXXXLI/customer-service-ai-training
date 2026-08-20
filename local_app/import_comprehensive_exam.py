from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/maxxxxx/Downloads/秀域企业完整知识库_十模块高频QA综合测试_2026年8月.md")
KB = ROOT / "knowledge_base"
STATIC = ROOT / "local_app" / "static" / "data"

MODULE_IDS = [f"MOD-{index:02d}" for index in range(1, 11)]
DOMAINS = [
    "enterprise_service", "customer_service", "point_wave", "super_v", "weight_management",
    "glp1_medical", "body_management", "skin_hair", "spring_face_medical_beauty", "private_health",
]


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("**", "")).strip()


def bullets(block: str) -> list[str]:
    return [clean(re.sub(r"^\s*-\s*", "", line)) for line in block.splitlines() if re.match(r"^\s*-\s+", line)]


def section(block: str, title: str, next_titles: tuple[str, ...]) -> str:
    start = re.search(rf"(?m)^\*\*{re.escape(title)}：\*\*\n", block)
    if not start:
        return ""
    tail = block[start.end():]
    stops = "|".join(rf"^\*\*{re.escape(item)}：\*\*" for item in next_titles)
    end = re.search(rf"(?m){stops}", tail) if stops else None
    return tail[:end.start()] if end else tail


def parse_fill_questions(text: str, answers: list[str]) -> list[dict]:
    lines = [clean(line) for line in text.splitlines() if re.match(r"^\d+\.\s", line)]
    return [{"id": f"F{index:02d}", "prompt": re.sub(r"^\d+\.\s*", "", line), "answers": [answers[index - 1]]}
            for index, line in enumerate(lines, 1) if index <= 6]


def parse_choice_questions(text: str, answers: list[str]) -> list[dict]:
    pattern = re.compile(r"(?ms)^([1-8])\.\s*\*\*【(单选|多选)】\*\*\s*(.*?)(?=^\d+\.\s*\*\*【|\Z)")
    rows = []
    for number, kind, body in pattern.findall(text):
        question, _, options = body.partition("\n")
        prompt = question
        correct = re.match(r"([A-D、]+)", answers[int(number) - 1])
        rows.append({
            "id": f"C{int(number):02d}", "kind": "multiple" if kind == "多选" else "single",
            "prompt": clean(prompt),
            "options": [{"key": key, "text": clean(body)} for key, body in re.findall(r"(?m)^\s*-\s*([A-D])\.\s*(.*)$", options)],
            "answers": re.findall(r"[A-D]", correct.group(1)) if correct else [],
            "explanation": clean(re.sub(r"^[A-D、]+。?\s*", "", answers[int(number) - 1])),
        })
    if len(rows) != 8:
        raise RuntimeError(f"expected 8 choices, got {len(rows)}")
    return rows


def parse_scenarios(prompt_block: str, scoring_block: str, module_index: int) -> list[dict]:
    prompts = {int(number): {"title": clean(title), "task": clean(task), "opening": clean(opening).removeprefix("顾客：")}
               for number, title, task, opening in re.findall(r"(?ms)^#### 场景(\d+)｜(.+?)\n.*?- \*\*考生任务：\*\*\s*(.*?)\n.*?- \*\*顾客开场：\*\*\s*顾客：(.*?)(?=\n\n|\Z)", prompt_block)}
    chunks = re.split(r"(?m)^#### 场景(\d+)｜", scoring_block)[1:]
    scenarios = []
    for offset in range(0, len(chunks), 2):
        number = int(chunks[offset])
        block = chunks[offset + 1]
        base = prompts[number]
        hidden = bullets(section(block, "AI顾客隐藏信息", ("信息释放规则", "参考多轮对话", "必须覆盖的标准答案要点")))
        release = bullets(section(block, "信息释放规则", ("参考多轮对话", "必须覆盖的标准答案要点")))
        required = bullets(section(block, "必须覆盖的标准答案要点", ("关键失败", "本场景AI评分维度")))
        critical = bullets(section(block, "关键失败", ("本场景AI评分维度",)))
        reference = clean(section(block, "参考多轮对话", ("必须覆盖的标准答案要点",)))
        cue = f"{base['title']} {base['opening']} {' '.join(hidden)}"
        if re.search(r"价格|优惠|券|贵|抵扣", cue):
            objections = ["怕被推销", "担心价格", "想确认当前规则"]
        elif re.search(r"疼|晕|不适|出血|炎症|硬结|呕吐|麻木", cue):
            objections = ["担心异常", "怕疼", "想尽快处理"]
        elif re.search(r"药|注射|GLP", cue, re.I):
            objections = ["担心副作用", "不想被随便推荐", "想知道后续安排"]
        elif re.search(r"私密|隐私", cue):
            objections = ["担心隐私", "怕疼", "不想被强推"]
        else:
            objections = ["怕被推销", "想先听懂再决定", "担心效果"]
        scenarios.append({
            "id": f"SCN-CEX-M{module_index:02d}-S{number:02d}", "module_id": MODULE_IDS[module_index - 1],
            "module_title": "", "domain": DOMAINS[module_index - 1], "scenario_number": number,
            "title": base["title"], "task": base["task"], "opening": base["opening"],
            "persona": {"age": 36, "gender": "女", "occupation": "顾客", "style": "谨慎、会追问", "goal": base["title"], "knowledge_level": "普通顾客"},
            "hidden_objections": objections, "hidden_information": hidden, "information_release_rules": release, "must_test": required,
            "critical_failures": critical, "reference_answer": reference, "source": SOURCE.name,
        })
    if len(scenarios) != 3:
        raise RuntimeError(f"expected 3 scenarios, got {len(scenarios)}")
    return scenarios


def parse() -> dict:
    text = SOURCE.read_text(encoding="utf-8")
    suites = re.split(r"(?m)^# 第[一二三四五六七八九十]+套｜", text)[1:]
    titles = re.findall(r"(?m)^# 第[一二三四五六七八九十]+套｜(.+)$", text)
    modules, scenarios = [], []
    for index, (title, suite) in enumerate(zip(titles, suites), 1):
        question_part, answer_part = suite.split("## 二、标准答案与评分依据", 1)
        fill_prompt = re.search(r"(?ms)^### 第一部分｜填空题.*?\n(.*?)(?=^### 第二部分)", question_part).group(1)
        choice_prompt = re.search(r"(?ms)^### 第二部分｜选择题.*?\n(.*?)(?=^### 第三部分)", question_part).group(1)
        scenario_prompt = re.search(r"(?ms)^### 第三部分｜AI多轮对话.*?\n(.*)\Z", question_part).group(1)
        fill_answers = [clean(re.sub(r"^\d+\.\s*", "", line)) for line in re.search(r"(?ms)^### 第一部分｜填空题答案\n(.*?)(?=^### 第二部分)", answer_part).group(1).splitlines() if re.match(r"^\d+\.\s", line)]
        choice_answers = [clean(re.sub(r"^\d+\.\s*", "", line)) for line in re.search(r"(?ms)^### 第二部分｜选择题答案\n(.*?)(?=^### 第三部分)", answer_part).group(1).splitlines() if re.match(r"^\d+\.\s", line)]
        scenario_scoring = re.search(r"(?ms)^### 第三部分｜AI多轮对话标准答案与评分\n(.*?)(?=^## 三、本套成绩计算)", answer_part).group(1)
        current_scenarios = parse_scenarios(scenario_prompt, scenario_scoring, index)
        for scenario in current_scenarios:
            scenario["module_title"] = clean(title)
        modules.append({"id": MODULE_IDS[index - 1], "title": clean(title), "fill_blanks": parse_fill_questions(fill_prompt, fill_answers), "choices": parse_choice_questions(choice_prompt, choice_answers), "scenarios": current_scenarios})
        scenarios.extend(current_scenarios)
    if len(modules) != 10 or len(scenarios) != 30:
        raise RuntimeError(f"expected 10 modules / 30 scenarios, got {len(modules)} / {len(scenarios)}")
    return {"version": "2026-08-comprehensive-exam", "title": "秀域企业完整知识库｜十模块高频QA综合测试", "modules": modules}


def main() -> None:
    bank = parse()
    scenarios = [scenario for module in bank["modules"] for scenario in module["scenarios"]]
    KB.joinpath("comprehensive_exam_bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    KB.joinpath("scenario_library.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in scenarios) + "\n", encoding="utf-8")
    STATIC.mkdir(parents=True, exist_ok=True)
    STATIC.joinpath("comprehensive_exam_bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATIC.joinpath("scenario_library.jsonl").write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in scenarios) + "\n", encoding="utf-8")
    print(json.dumps({"modules": len(bank["modules"]), "scenarios": len(scenarios)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
