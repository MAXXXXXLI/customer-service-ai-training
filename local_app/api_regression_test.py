from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path


BASE_URL = "http://127.0.0.1:8787/api/chat"
REPORT_PATH = Path(__file__).resolve().parent / "api_regression_report.json"
CATALOG_PATH = Path(__file__).resolve().parent.parent / "knowledge_base" / "learning_catalog.json"
COURSE_TITLES = {item["title"] for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["courses"]}
FORBIDDEN = re.compile(
    r"(?:SRC-\d+|CHUNK-\d+|document_id|source_id|"
    r"\b(?:FLOW|PROD|OP|KNOW|SERVICE|OPS|COMPLIANCE|OB)-[A-Z0-9-]+\b|"
    r"[^，。；：\n\"]{1,80}\.(?:docx?|pptx?|xlsx?|xls|pdf|mp4)\b)",
    flags=re.I,
)
SEMANTIC_RISK = re.compile(
    r"(?:单次治疗|后续疗程|按疗程|进入疗程|"
    r"压迫.{0,8}(?:血管|神经)|脑部.{0,8}(?:供血|供氧)|"
    r"供血供氧.{0,8}不足|(?:可能)?涉及.{0,6}(?:神经|血管)|"
    r"检查.{0,8}(?:僵硬程度|结节|体征))",
    flags=re.I,
)
ASSESSMENT_ADVICE = re.compile(r"(?:古方|口服|注射|用药|药品|剂量|停药|隔天一次|每天\s*\d+\s*次)", re.I)


def post(payload):
    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


cases = []

qa = post({
    "mode": "qa",
    "action": "turn",
    "message": "顾客问：这个项目做一次是不是一定有效？员工应该怎么回答？",
    "history": [],
})
cases.append({"name": "knowledge_advisor", "response": qa})

training_history = [
    {"role": "assistant", "content": "我低头工作久了肩颈很硬，偶尔头晕，你们这个是不是能治颈椎病？"},
]
training = post({
    "mode": "training",
    "action": "turn",
    "message": "我先了解一下，头晕多久了，最近有没有突然加重，是否伴随手脚麻木无力？我们不做疾病诊断，如果症状明显建议先做医疗评估。",
    "history": training_history,
})
cases.append({"name": "scenario_coaching", "response": training})

test_history = [
    {"role": "assistant", "content": "我每天上班，没时间来店里，你们能保证一个月瘦十斤吗？"},
]
test_turn = post({
    "mode": "test",
    "action": "turn",
    "scenario_id": "SCN-SLIM-01",
    "message": "我理解您想尽快看到变化。先了解一下您的作息、饮食和之前尝试过的方法，再看什么目标更适合；我们不能承诺固定减重斤数。",
    "history": test_history,
})
cases.append({"name": "assessment_customer_turn", "response": test_turn})

full_history = [
    *test_history,
    {"role": "user", "content": "我理解您想尽快看到变化。先了解一下您的作息、饮食和之前尝试过的方法，再看什么目标更适合；我们不能承诺固定减重斤数。"},
    {"role": "assistant", "content": test_turn["result"]["reply"]},
    {"role": "user", "content": "您更担心没有效果，还是没有时间执行？我们可以先把目标拆成阶段指标，再选择适合您节奏的下一步。"},
]
assessment = post({
    "mode": "test",
    "action": "finish",
    "scenario_id": "SCN-SLIM-01",
    "history": full_history,
})
cases.append({"name": "assessment_report", "response": assessment})

checks = {
    "qa_has_answer": bool(qa.get("result", {}).get("answer")),
    "qa_has_method_route": all(key in qa.get("result", {}).get("route", {}) for key in ["intent", "primary_module", "supporting_modules", "courses", "method_step"]),
    "qa_effect_question_uses_objection_and_safety": qa.get("result", {}).get("route", {}).get("primary_module") == "异议沟通与下一步" and "安全、同意与合规服务" in qa.get("result", {}).get("route", {}).get("supporting_modules", []),
    "qa_has_recommended_next_action": bool(qa.get("result", {}).get("recommended_action")),
    "qa_has_friendly_citations": bool(qa.get("citations")) and all(set(item) <= {"label", "category", "module", "chapter"} for item in qa["citations"]),
    "qa_references_open_learning_courses": bool(qa.get("retrieved")) and all(item.get("title") in COURSE_TITLES for item in qa["retrieved"]),
    "training_has_customer_reply": bool(training.get("result", {}).get("customer_reply")),
    "training_has_structured_feedback": all(key in training.get("result", {}).get("feedback", {}) for key in ["level", "issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal"]),
    "training_hides_retrieval_details": not training.get("citations") and not training.get("retrieved"),
    "test_turn_has_no_feedback": "feedback" not in test_turn.get("result", {}),
    "test_turn_has_no_hint_metadata": not test_turn.get("citations") and not test_turn.get("retrieved"),
    "assessment_has_100_point_score": isinstance(assessment.get("result", {}).get("total_score"), (int, float)) and 0 <= assessment["result"]["total_score"] <= 100,
    "assessment_has_seven_dimensions": len(assessment.get("result", {}).get("dimension_scores", [])) == 7,
}

for case in cases:
    public_text = json.dumps({key: value for key, value in case["response"].items() if key != "meta"}, ensure_ascii=False)
    matches = sorted(set(FORBIDDEN.findall(public_text)))
    case["forbidden_matches"] = matches
    case["semantic_risk_matches"] = sorted(set(match.group(0) for match in SEMANTIC_RISK.finditer(public_text)))
checks["no_raw_file_or_internal_names"] = all(not case["forbidden_matches"] for case in cases)
checks["no_unsafe_medical_inference"] = all(not case["semantic_risk_matches"] for case in cases)
assessment_advice_text = json.dumps({
    "comments": [item.get("comment", "") for item in assessment.get("result", {}).get("dimension_scores", [])],
    "improvements": assessment.get("result", {}).get("improvements", []),
    "summary": assessment.get("result", {}).get("summary", ""),
}, ensure_ascii=False)
checks["assessment_has_no_unverified_product_advice"] = not ASSESSMENT_ADVICE.search(assessment_advice_text)

report = {
    "status": "passed" if all(checks.values()) else "failed",
    "checks": checks,
    "cases": cases,
}
REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "checks": checks, "report": str(REPORT_PATH)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "passed" else 1)
