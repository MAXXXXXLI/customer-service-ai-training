from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import server


API_KEY = os.getenv("SILICONFLOW_API_KEY", "").strip()
DEFAULT_MODEL = os.getenv("SILICONFLOW_TEST_MODEL", "Qwen/Qwen3.5-35B-A3B")
SECONDARY_MODEL = os.getenv("SILICONFLOW_SECONDARY_MODEL", "deepseek-ai/DeepSeek-V3.2")
REPORT_PATH = Path(__file__).resolve().parent / "full_function_regression_report.json"
INTERNAL_MARKERS = re.compile(r"考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练", re.I)


if not API_KEY:
    raise SystemExit("请通过 SILICONFLOW_API_KEY 环境变量提供测试 Key。")


results: list[dict[str, Any]] = []


def record(name: str, checks: dict[str, bool], details: dict[str, Any] | None = None) -> None:
    results.append({"name": name, "passed": all(checks.values()), "checks": checks, "details": details or {}})


def call(payload: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    return server.handle_chat({**payload, "api_key": API_KEY, "model": model})


def run(name: str, operation: Callable[[], None]) -> None:
    print(f"[RUN] {name}", flush=True)
    try:
        operation()
    except Exception as exc:  # keep the rest of the suite running
        results.append({"name": name, "passed": False, "checks": {"exception": False}, "details": {"error": str(exc)}})
    print(f"[{'PASS' if results[-1]['passed'] else 'FAIL'}] {name}", flush=True)


def test_learning_and_models() -> None:
    catalog = server.LEARNING_CATALOG
    model_ids = {item["id"] for item in server.AVAILABLE_MODELS}
    checks = {
        "learning_modules_present": len(server.LEARNING_MODULES) == 7,
        "courses_present": len(catalog.get("courses", [])) >= 30,
        "scenarios_present": len(server.SCENARIOS) >= 10,
        "default_model_available": DEFAULT_MODEL in model_ids,
        "secondary_model_available": SECONDARY_MODEL in model_ids,
        "model_choices_multiple": len(model_ids) >= 5,
    }
    record("learning_and_model_catalog", checks, {"modules": len(server.LEARNING_MODULES), "courses": len(catalog.get("courses", [])), "models": sorted(model_ids)})


def test_all_selectable_models() -> None:
    checks = {}
    returned_models = {}
    for item in server.AVAILABLE_MODELS:
        model = item["id"]
        raw, meta = server.call_model(
            "你只做连接测试，严格输出 JSON：{\"ok\":true}",
            [{"role": "user", "content": "返回连接测试结果。"}],
            model,
            API_KEY,
            temperature=0.0,
            max_tokens=80,
        )
        checks[model] = (server.extract_json(raw) or {}).get("ok") is True
        returned_models[model] = meta.get("model")
    record("all_selectable_models", checks, {"returned_models": returned_models})


def test_qa_and_secondary_model() -> None:
    qa = call({"mode": "qa", "action": "turn", "message": "我第一次来，也不知道适合什么，可以直接给我推荐吗？", "history": []})
    qa_alt = call({"mode": "qa", "action": "turn", "message": "体验过程中觉得烫或头晕应该怎么办？", "history": []}, SECONDARY_MODEL)
    checks = {
        "default_real_model": qa.get("meta", {}).get("mock") is False,
        "default_answer_present": len(qa.get("result", {}).get("answer", "")) >= 20,
        "default_route_present": bool(qa.get("result", {}).get("route", {}).get("primary_module")),
        "default_next_action": bool(qa.get("result", {}).get("recommended_action")),
        "secondary_real_model": qa_alt.get("meta", {}).get("mock") is False,
        "secondary_answer_present": len(qa_alt.get("result", {}).get("answer", "")) >= 20,
        "secondary_safety_content": bool(re.search(r"暂停|停止|不舒服|医疗|评估", qa_alt.get("result", {}).get("answer", ""))),
    }
    record("qa_default_and_secondary_model", checks, {"default_model": qa.get("meta", {}).get("model"), "secondary_model": qa_alt.get("meta", {}).get("model"), "answers": [qa.get("result", {}).get("answer"), qa_alt.get("result", {}).get("answer")]})


def test_training_multiturn() -> None:
    scenario = server.scenario_by_id("SCN-PAIN-01")
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee_turns = [
        "我理解您担心颈椎问题。先确认一下，头晕持续多久了，最近有没有加重，是否伴随胸痛、呼吸困难或手脚麻木无力？",
        "谢谢您说明。除了久坐更明显，睡眠和日常活动受影响吗？以前做过哪些处理？",
        "我不能诊断颈椎病或承诺效果。先完成安全信息和目标确认；如果症状明显或加重，建议先做医疗评估。",
    ]
    customer_replies = []
    feedbacks = []
    for employee in employee_turns:
        response = call({"mode": "training", "action": "turn", "scenario_id": scenario["id"], "message": employee, "history": history})
        result = response.get("result", {})
        reply = result.get("customer_reply", "")
        customer_replies.append(reply)
        feedbacks.append(result.get("feedback", {}))
        history.extend([{"role": "user", "content": employee}, {"role": "assistant", "content": reply}])

    unsafe = call({"mode": "training", "action": "turn", "scenario_id": scenario["id"], "message": "这个项目肯定能治好颈椎病，保证百分百有效。", "history": [{"role": "assistant", "content": scenario["opening"]}]})
    checks = {
        "three_replies_present": all(customer_replies),
        "replies_are_unique": len(set(customer_replies)) == len(customer_replies),
        "opening_not_repeated": scenario["opening"] not in customer_replies,
        "role_did_not_drift": all(not INTERNAL_MARKERS.search(reply) for reply in customer_replies),
        "feedback_complete": all(all(key in feedback for key in ["level", "issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal"]) for feedback in feedbacks),
        "unsafe_turn_is_critical": unsafe.get("result", {}).get("feedback", {}).get("level") == "critical",
    }
    record("training_multiturn_and_critical_feedback", checks, {"customer_replies": customer_replies, "feedback_levels": [item.get("level") for item in feedbacks], "unsafe_level": unsafe.get("result", {}).get("feedback", {}).get("level")})


def test_assessment_multiturn_and_report() -> None:
    scenario = server.scenario_by_id("SCN-SLIM-01")
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee_turns = [
        "我理解您时间少，也希望尽快看到变化。先了解一下您的作息、饮食、活动和以前尝试过的方法，可以吗？",
        "听起来时间和反弹都是您的顾虑。您更希望先改善体重趋势，还是穿衣感受？每周能安排多少时间？",
        "我们不能保证一个月固定瘦十斤，也不能承诺不反弹。可以先确定一个可观察的阶段目标，再按您的时间安排体验和复盘。",
        "如果您愿意，下一步先确认健康情况、预算和可到店时间，再给您两种可选择的安排，您看可以吗？",
    ]
    customer_replies = []
    turn_shapes = []
    for employee in employee_turns:
        response = call({"mode": "test", "action": "turn", "scenario_id": scenario["id"], "message": employee, "history": history})
        result = response.get("result", {})
        reply = result.get("reply", "")
        customer_replies.append(reply)
        turn_shapes.append(sorted(result.keys()))
        history.extend([{"role": "user", "content": employee}, {"role": "assistant", "content": reply}])

    report = call({"mode": "test", "action": "finish", "scenario_id": scenario["id"], "history": history})
    assessment = report.get("result", {})
    dimensions = assessment.get("dimension_scores", [])
    expected = [(item["id"], item["name"], item["weight"]) for item in server.RUBRIC["dimensions"]]
    actual = [(item.get("id"), item.get("name"), item.get("max_score")) for item in dimensions]
    calculated_total = sum(item.get("score", 0) for item in dimensions)
    caps = [item.get("score_cap", 100) for item in assessment.get("critical_failures", [])]
    expected_total = min([calculated_total, *caps])
    checks = {
        "four_replies_present": all(customer_replies),
        "replies_are_unique": len(set(customer_replies)) == len(customer_replies),
        "opening_not_repeated": scenario["opening"] not in customer_replies,
        "role_did_not_drift": all(not INTERNAL_MARKERS.search(reply) for reply in customer_replies),
        "turn_has_only_customer_fields": all(set(shape) <= {"reply", "emotion", "should_continue"} for shape in turn_shapes),
        "exact_seven_dimensions": len(dimensions) == 7 and actual == expected,
        "dimension_evidence_present": all(item.get("evidence") and item.get("comment") for item in dimensions),
        "evidence_uses_employee_only": all(not server.evidence_uses_customer_only_text(item.get("evidence", ""), history) for item in dimensions),
        "total_is_recalculated": assessment.get("total_score") == expected_total,
        "report_sections_present": all(assessment.get(key) for key in ["strengths", "improvements", "summary"]),
    }
    record("assessment_multiturn_and_report", checks, {"customer_replies": customer_replies, "total_score": assessment.get("total_score"), "dimension_scores": dimensions, "critical_failures": assessment.get("critical_failures", []), "summary": assessment.get("summary")})


def test_assessment_critical_cap() -> None:
    scenario = server.scenario_by_id("SCN-SLIM-01")
    history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": "可以保证一个月瘦十斤，而且百分百不反弹，你今天就买。"},
        {"role": "assistant", "content": "你真的能保证吗？"},
    ]
    report = call({"mode": "test", "action": "finish", "scenario_id": scenario["id"], "history": history})
    assessment = report.get("result", {})
    codes = {item.get("code") for item in assessment.get("critical_failures", [])}
    checks = {
        "cf02_detected": "CF-02" in codes,
        "score_cap_applied": assessment.get("total_score", 100) <= 69,
        "seven_dimensions_kept": len(assessment.get("dimension_scores", [])) == 7,
    }
    record("assessment_critical_failure_cap", checks, {"total_score": assessment.get("total_score"), "critical_failures": assessment.get("critical_failures", [])})


run("learning_and_model_catalog", test_learning_and_models)
run("all_selectable_models", test_all_selectable_models)
run("qa_default_and_secondary_model", test_qa_and_secondary_model)
run("training_multiturn_and_critical_feedback", test_training_multiturn)
run("assessment_multiturn_and_report", test_assessment_multiturn_and_report)
run("assessment_critical_failure_cap", test_assessment_critical_cap)

report = {"status": "passed" if all(item["passed"] for item in results) else "failed", "models_tested": [item["id"] for item in server.AVAILABLE_MODELS], "cases": results}
REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "models_tested": report["models_tested"], "cases": [{"name": item["name"], "passed": item["passed"], "checks": item["checks"]} for item in results], "report": str(REPORT_PATH)}, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "passed" else 1)
