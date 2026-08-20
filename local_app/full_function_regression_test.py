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


def exact_scenario(scenario_id: str) -> dict[str, Any]:
    """Resolve a test fixture without scenario_by_id's first-item fallback."""
    scenario = next((item for item in server.SCENARIOS if item.get("id") == scenario_id), None)
    if scenario is None:
        available = ", ".join(sorted(str(item.get("id")) for item in server.SCENARIOS))
        raise AssertionError(f"测试场景不存在：{scenario_id}；当前有效 ID：{available}")
    return scenario


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
    catalog_groups = [group for module in catalog.get("module_index", []) for group in module.get("groups", [])]
    checks = {
        "ten_learning_modules_present": len(server.LEARNING_MODULES) == 10,
        "forty_three_courses_present": len(catalog.get("courses", [])) == 43,
        "ten_course_chapters_present": len(catalog_groups) == 10,
        "thirty_scenarios_present": len(server.SCENARIOS) == 30,
        "default_model_available": DEFAULT_MODEL in model_ids,
        "secondary_model_available": SECONDARY_MODEL in model_ids,
        "model_choices_multiple": len(model_ids) >= 5,
    }
    record("learning_and_model_catalog", checks, {"modules": len(server.LEARNING_MODULES), "courses": len(catalog.get("courses", [])), "chapters": len(catalog_groups), "scenarios": len(server.SCENARIOS), "models": sorted(model_ids)})


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
    scenario = exact_scenario("SCN-CEX-M03-S01")
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee_turns = [
        "我理解您现在更痛会担心。先确认疼痛的位置、程度、从什么时候开始，是否持续加重；有没有胸痛、呼吸困难、晕厥或进行性麻木无力？",
        "谢谢您说明。今天先不继续安排操作，我会记录体验后的变化并升级负责人；如果疼痛明显、持续或加重，建议及时由医疗机构评估。",
        "门店不能判断是不是项目造成，也不能承诺治疗效果。安全情况确认后，我们再按记录和当前流程说明能够处理的下一步。",
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
    record("training_multiturn_and_critical_feedback", checks, {"scenario_id": scenario["id"], "customer_replies": customer_replies, "feedback_levels": [item.get("level") for item in feedbacks], "unsafe_level": unsafe.get("result", {}).get("feedback", {}).get("level")})


def test_assessment_multiturn_and_report() -> None:
    scenario = exact_scenario("SCN-CEX-M05-S01")
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee_turns = [
        "我理解您很配合却看到体重上涨会失望。先确认这两次是否在相同时间、相同衣着和相近状态下测量，可以吗？",
        "除了体重，这周的饮食、睡眠、活动、排便和生理期有没有变化？围度或衣服松紧有没有不同？",
        "单次体重会受多种因素影响，不能据此保证效果或判断原因。我们可以统一测量条件，同时看体重趋势、围度和体感。",
        "如果您愿意，下一步先记录本周情况，确定一个可执行动作和复查时间；有明显不适则先暂停并评估安全。",
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
    record("assessment_multiturn_and_report", checks, {"scenario_id": scenario["id"], "customer_replies": customer_replies, "total_score": assessment.get("total_score"), "dimension_scores": dimensions, "critical_failures": assessment.get("critical_failures", []), "summary": assessment.get("summary")})


def test_assessment_critical_cap() -> None:
    scenario = exact_scenario("SCN-CEX-M05-S03")
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
    record("assessment_critical_failure_cap", checks, {"scenario_id": scenario["id"], "total_score": assessment.get("total_score"), "critical_failures": assessment.get("critical_failures", [])})


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
