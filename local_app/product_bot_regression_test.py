from __future__ import annotations

import json
import re
from pathlib import Path

import server


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_FIELDS = {
    "level",
    "issue",
    "why",
    "method_step",
    "knowledge_focus",
    "suggested_reply",
    "next_goal",
}
ROLE_LEAK = re.compile(
    r"考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练|"
    r"SOP|设备参数|成分核对|建议您|请您|你应该"
)


checks: dict[str, bool] = {}
details: dict[str, object] = {}


def check(name: str, condition: bool, detail: object = "") -> None:
    checks[name] = bool(condition)
    if not condition:
        details[name] = detail


def run() -> None:
    original_mock = server.MOCK_MODE
    original_key = server.ENV_API_KEY
    original_call_model = server.call_model
    server.MOCK_MODE = True
    server.ENV_API_KEY = ""

    try:
        history = [
            {"role": "user", "content": "我胸闷气短还出冷汗，今天先做个超V可以吗？"},
            {"role": "assistant", "content": "先停止项目并确认安全。"},
        ]
        standalone = server.qa_context_query("无痕水光多少钱？", history)
        contextual = server.qa_context_query("那我现在应该怎么办？", history)
        check("qa_new_question_does_not_drag_old_context", standalone == "无痕水光多少钱？", standalone)
        check("qa_follow_up_inherits_customer_context", "胸闷气短" in contextual and "怎么办" in contextual, contextual)
        check("qa_retrieval_query_excludes_assistant_answer", "停止项目" not in contextual, contextual)

        first = server.handle_chat({
            "mode": "qa",
            "action": "turn",
            "message": "我胸闷气短还出冷汗，今天先做个超V可以吗？",
            "history": [],
        })
        first_answer = first["result"]["answer"]
        follow_up = server.handle_chat({
            "mode": "qa",
            "action": "turn",
            "message": "那我现在应该怎么办？",
            "history": [
                {"role": "user", "content": "我胸闷气短还出冷汗，今天先做个超V可以吗？"},
                {"role": "assistant", "content": first_answer},
            ],
        })
        follow_answer = follow_up["result"]["answer"]
        check("qa_red_flag_stops_service", bool(re.search(r"先不|停止|暂停|不要做", first_answer)), first_answer)
        check("qa_red_flag_recommends_medical_triage", bool(re.search(r"急救|医疗机构|就医|医院", first_answer)), first_answer)
        check("qa_red_flag_follow_up_is_contextual", bool(re.search(r"现在|急救|医疗机构|就医", follow_answer)), follow_answer)
        check("qa_red_flag_turns_are_not_repeated", first_answer != follow_answer, [first_answer, follow_answer])
        check(
            "qa_red_flag_routes_to_safety",
            first["result"]["route"]["primary_module"] == "企业治理与服务标准"
            and follow_up["result"]["route"]["primary_module"] == "企业治理与服务标准",
            [first["result"]["route"], follow_up["result"]["route"]],
        )

        qa_matrix = {
            "medicine": "司美格鲁肽应该打多少剂量？",
            "pregnancy": "我怀孕了能做这个项目吗？",
            "sensitive_skin": "敏感肌能做无痕水光吗？",
            "price": "无痕水光现在多少钱？",
            "guarantee": "这个项目做一次是不是一定有效？",
            "comparison": "超V和普通护理有什么区别？",
        }
        qa_results = {
            name: server.handle_chat({"mode": "qa", "action": "turn", "message": question, "history": []})
            for name, question in qa_matrix.items()
        }
        required_route_fields = {"intent", "primary_module", "supporting_modules", "courses", "method_step"}
        check(
            "qa_matrix_returns_complete_answers",
            all(item.get("result", {}).get("answer") for item in qa_results.values()),
            qa_results,
        )
        check(
            "qa_matrix_returns_method_routes",
            all(required_route_fields <= set(item.get("result", {}).get("route", {})) for item in qa_results.values()),
            {name: item.get("result", {}).get("route") for name, item in qa_results.items()},
        )
        check(
            "qa_medicine_has_no_dose_instruction",
            bool(re.search(r"不能|医生|药师|处方", qa_results["medicine"]["result"]["answer"]))
            and not re.search(r"\d+\s*(?:mg|毫克|支|次)", qa_results["medicine"]["result"]["answer"], re.I),
            qa_results["medicine"]["result"]["answer"],
        )
        check(
            "qa_special_population_is_not_auto_approved",
            bool(re.search(r"暂停|不能|确认|医生|专业", qa_results["pregnancy"]["result"]["answer"])),
            qa_results["pregnancy"]["result"]["answer"],
        )
        check(
            "qa_price_requests_current_store_context",
            all(word in qa_results["price"]["result"]["answer"] for word in ["门店", "项目"]),
            qa_results["price"]["result"]["answer"],
        )
        check(
            "qa_guarantee_avoids_promising_results",
            bool(re.search(r"不能承诺|不能保证|个体差异|不一定", qa_results["guarantee"]["result"]["answer"])),
            qa_results["guarantee"]["result"]["answer"],
        )

        captured: dict[str, object] = {}

        def fake_call_model(system: str, messages: list[dict[str, str]], model: str, api_key: str, **_: object):
            captured["system"] = system
            captured["messages"] = messages
            return json.dumps({
                "answer": "先停止项目并确认安全。",
                "uncertainties": [],
                "recommended_action": "",
            }, ensure_ascii=False), {"model": model}

        server.MOCK_MODE = False
        server.call_model = fake_call_model
        server.handle_chat({
            "mode": "qa",
            "action": "turn",
            "api_key": "regression-test-key",
            "message": "那我现在应该怎么办？",
            "history": history,
        })
        model_messages = captured.get("messages", [])
        check(
            "qa_real_model_receives_full_dialogue_history",
            [item.get("role") for item in model_messages] == ["user", "assistant", "user"],
            model_messages,
        )
        check(
            "qa_real_model_current_turn_has_route_and_retrieval",
            bool(model_messages)
            and "方法路由" in model_messages[-1].get("content", "")
            and "检索资料" in model_messages[-1].get("content", ""),
            model_messages[-1] if model_messages else [],
        )
        server.MOCK_MODE = True
        server.call_model = original_call_model

        employee_turns = [
            "您好，我先了解一下，您现在最想改善的是什么？",
            "这种情况大概多久了，对日常有什么影响？",
            "我理解您的担心。除了这个，您最顾虑的是时间、感受还是预算？",
            "我不能承诺固定效果，会先确认适用情况，再给您可以选择的下一步。",
        ]
        role_failures = []
        continuity_failures = []
        feedback_failures = []
        for scenario in server.SCENARIOS:
            scenario_id = scenario["id"]
            for mode in ("training", "test"):
                start = server.handle_chat({"mode": mode, "action": "start", "scenario_id": scenario_id})
                dialogue = [{"role": "assistant", "content": start["message"]}]
                replies = []
                for employee_turn in employee_turns:
                    response = server.handle_chat({
                        "mode": mode,
                        "action": "turn",
                        "scenario_id": scenario_id,
                        "message": employee_turn,
                        "history": dialogue,
                    })
                    key = "customer_reply" if mode == "training" else "reply"
                    reply = response["result"][key]
                    replies.append(reply)
                    if ROLE_LEAK.search(reply) or len(reply) > 100 or reply.count("？") + reply.count("?") > 1:
                        role_failures.append({"scenario": scenario_id, "mode": mode, "reply": reply})
                    if mode == "training" and not FEEDBACK_FIELDS <= set(response["result"].get("feedback", {})):
                        feedback_failures.append({"scenario": scenario_id, "feedback": response["result"].get("feedback")})
                    dialogue.extend([
                        {"role": "user", "content": employee_turn},
                        {"role": "assistant", "content": reply},
                    ])
                if len(set(replies)) != len(replies) or replies[0] == start["message"]:
                    continuity_failures.append({"scenario": scenario_id, "mode": mode, "replies": replies})
        check("all_scenarios_customer_role_is_stable", not role_failures, role_failures)
        check("all_scenarios_have_unique_continuous_replies", not continuity_failures, continuity_failures)
        check("all_training_turns_have_complete_feedback", not feedback_failures, feedback_failures)

        # A vague affirmative is not an answer to the customer's current question.
        # This was the regression shown in the reported screenshot: "有的，有的"
        # incorrectly advanced straight to the next hidden objection.
        scenario = server.SCENARIOS[0]
        opening_history = [{"role": "assistant", "content": scenario["opening"]}]
        vague_messages = ["有的，有的", "有的", "可以", "今天下雨"]
        vague_replies = {
            message: server.test_fallback_reply(scenario, opening_history, message)
            for message in vague_messages
        }
        check(
            "customer_does_not_advance_after_vague_affirmation",
            all("具体" in reply and "办法" in reply and "怕疼" not in reply for reply in vague_replies.values()),
            vague_replies,
        )
        all_scenario_vague_failures = []
        for candidate in server.SCENARIOS:
            candidate_history = [{"role": "assistant", "content": candidate["opening"]}]
            for message in vague_messages:
                candidate_reply = server.test_fallback_reply(candidate, candidate_history, message)
                if "具体" not in candidate_reply or ("办法" not in candidate_reply and "说说" not in candidate_reply):
                    all_scenario_vague_failures.append({"scenario": candidate["id"], "message": message, "reply": candidate_reply})
        check("all_scenarios_hold_on_vague_employee_answers", not all_scenario_vague_failures, all_scenario_vague_failures)
        off_topic_method_reply = "我理解你比较怕疼，过程中我会先确认感受，不舒服就立刻停下。"
        off_topic_result = server.test_fallback_reply(scenario, opening_history, off_topic_method_reply)
        check(
            "method_question_rejects_off_topic_safety_reply",
            "具体" in off_topic_result and "办法" in off_topic_result and "怕疼" not in off_topic_result,
            off_topic_result,
        )
        model_jump = server.normalized_customer_reply(
            "我比较怕疼，过程中会不会很难受？",
            scenario,
            opening_history,
            "有的，有的",
        )
        check(
            "real_model_hidden_objection_jump_is_blocked",
            "具体" in model_jump and "办法" in model_jump and "怕疼" not in model_jump,
            model_jump,
        )
        held_history = [
            *opening_history,
            {"role": "user", "content": "有的，有的"},
            {"role": "assistant", "content": vague_replies["有的，有的"]},
        ]
        after_detail = server.test_fallback_reply(
            scenario,
            held_history,
            "我们会先了解你的肩颈情况，再介绍适合的体验方式和注意事项。",
        )
        check(
            "clarification_turn_does_not_skip_first_hidden_objection",
            "怕被推销" in after_detail,
            after_detail,
        )

        unsafe_training = server.normalize_training_result(
            {"customer_reply": "那听起来挺厉害的。", "feedback": {}},
            server.SCENARIOS[0],
            [],
            "这个能治好你的颈椎病，保证一次见效。",
        )
        check(
            "training_unsafe_claim_is_critical",
            unsafe_training["feedback"]["level"] == "critical",
            unsafe_training["feedback"],
        )
        check(
            "training_malformed_feedback_is_repaired",
            FEEDBACK_FIELDS <= set(unsafe_training["feedback"]),
            unsafe_training["feedback"],
        )

        assessment_history = [
            {"role": "assistant", "content": "我现在胸痛、呼吸困难，还一直出冷汗。"},
            {"role": "user", "content": "没事，这是正常现象，可以继续做，先安排项目。"},
        ]
        assessment = server.normalize_assessment_result(
            {"dimension_scores": [{"id": "D1", "score": 999, "evidence": ""}]},
            assessment_history,
        )
        check("assessment_always_has_seven_dimensions", len(assessment["dimension_scores"]) == 7, assessment)
        check("assessment_detects_critical_failure", bool(assessment["critical_failures"]), assessment)
        score_cap = min(item["score_cap"] for item in assessment["critical_failures"])
        check("assessment_applies_critical_score_cap", assessment["total_score"] <= score_cap, assessment)
        check(
            "assessment_score_dimensions_are_bounded",
            all(0 <= item["score"] <= item["max_score"] for item in assessment["dimension_scores"]),
            assessment["dimension_scores"],
        )

        app_js = (ROOT / "local_app" / "static" / "app.js").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        styles = (ROOT / "local_app" / "static" / "styles.css").read_text(encoding="utf-8")
        check(
            "static_site_loads_methodology_and_contextual_qa",
            "customer_service_methodology.json" in app_js
            and "staticQaQuery" in app_js
            and "cleanStaticHistory" in app_js,
        )
        check(
            "pages_deploys_methodology_data",
            "cp knowledge_base/customer_service_methodology.json _site/data/" in workflow,
        )
        check(
            "static_retrieval_excludes_raw_sources",
            'metadata.doc_type === "source"' in app_js,
        )
        check(
            "training_last_turn_can_be_revised_and_reevaluated",
            all(marker in app_js for marker in [
                "reviseLastTrainingTurn",
                'state.history.splice(-2, 2)',
                "修改本轮回复",
                "发送后重新评价",
            ])
            and ".revise-turn-button" in styles,
        )
    finally:
        server.MOCK_MODE = original_mock
        server.ENV_API_KEY = original_key
        server.call_model = original_call_model

    passed = sum(checks.values())
    total = len(checks)
    print(json.dumps({
        "status": "passed" if passed == total else "failed",
        "passed": passed,
        "total": total,
        "failed": [name for name, ok in checks.items() if not ok],
        "details": details,
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == total else 1)


if __name__ == "__main__":
    run()
