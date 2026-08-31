from __future__ import annotations

import json
import re
from pathlib import Path

import server


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "local_app" / "static" / "app.js").read_text(encoding="utf-8")
QUESTION_MARKS = re.compile(r"[？?]")
PROFESSIONAL_DRIFT = re.compile(
    r"适用性确认|专业评估|医疗评估|红旗|禁忌|SOP|成分核对|设备型号|阶段指标|复盘|"
    r"治疗史|特殊护肤品|强刺激产品|作用原理|工作原理|操作流程|测温|设备参数|产品机制|"
    r"(?:建议|请)您|我建议(?:你|您)|你(?:应该|需要).{0,12}(?:询问|确认|了解|评估|说明)|"
    r"您.{0,18}(?:有没有|是否|做过|用过|最近一次|病史|过敏史)",
    re.I,
)


def assert_customer_like(reply: str) -> None:
    assert reply, "customer reply is empty"
    assert len(reply) <= 100, reply
    assert len(QUESTION_MARKS.findall(reply)) <= 1, reply
    assert not server.TEST_INTERNAL_MARKERS.search(reply), reply
    assert not PROFESSIONAL_DRIFT.search(reply), reply


def exact_scenario(scenario_id: str) -> dict:
    scenario = next((item for item in server.SCENARIOS if item.get("id") == scenario_id), None)
    assert scenario is not None, f"测试场景不存在：{scenario_id}"
    return scenario


def test_scenario_knowledge_boundaries() -> None:
    assert len(server.SCENARIOS) == 30
    for scenario in server.SCENARIOS:
        assert scenario.get("persona", {}).get("knowledge_level"), scenario["id"]
        context = server.customer_turn_context(scenario)
        serialized = json.dumps(context, ensure_ascii=False)
        assert "must_test" not in context
        assert "must_test" not in serialized
        assert not any(rule in serialized for rule in scenario.get("must_test", []))

    beauty = exact_scenario("SCN-CEX-M08-S01")
    assert "纳米喷射" in beauty["opening"]
    assert "补水" in beauty["opening"]


def test_role_drift_is_repaired() -> None:
    scenario = exact_scenario("SCN-CEX-M08-S01")
    history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": "没什么不同，敏感肌不能做。"},
        {"role": "assistant", "content": "您这么说我不能接受，那您刚才还问什么？"},
        {"role": "user", "content": "我错了。"},
    ]
    drifted = {
        "reply": "既然知道错了，那您能具体说说之前做过什么敏感肌治疗吗？最近有没有用过什么特殊护肤品？",
        "emotion": "curious",
        "should_continue": True,
    }
    normalized = server.normalize_test_turn_result(drifted, scenario, history, "我错了。")
    assert normalized["reply"] != drifted["reply"]
    assert "重新给我讲清楚" in normalized["reply"]
    assert_customer_like(normalized["reply"])

    training = server.normalize_training_result(
        {"customer_reply": drifted["reply"], "feedback": {"level": "needs_work", "issue": "回答有误"}},
        scenario,
        history,
        "我错了。",
    )
    assert training["feedback"]["issue"] == "回答有误"
    assert_customer_like(training["customer_reply"])


def test_natural_customer_reply_is_preserved() -> None:
    # Structural release isolation intentionally replaces every model-authored
    # turn when a scenario carries release rules.  Candidate preservation is
    # still required for ordinary scenarios with no hidden release contract.
    scenario = {
        **exact_scenario("SCN-CEX-M03-S02"),
        "id": "SCN-NO-RELEASE-RULES",
        "hidden_information": [],
        "information_release_rules": [],
    }
    natural = "大概有半年了，低头久了会更明显。"
    normalized = server.normalize_test_turn_result({"reply": natural}, scenario, [{"role": "assistant", "content": scenario["opening"]}], "这种情况多久了？")
    assert normalized["reply"] == natural
    assert_customer_like(normalized["reply"])


def test_training_feedback_does_not_penalize_future_fact() -> None:
    scenario = exact_scenario("SCN-CEX-M03-S01")
    history = [{"role": "assistant", "content": scenario["opening"]}]
    result = server.normalize_training_result(
        {
            "customer_reply": "昨晚开始疼，今天手臂突然有点发麻。",
            "feedback": {
                "level": "critical",
                "issue": "员工未识别顾客手臂发麻这一红旗症状。",
                "why": "顾客已经表达手臂麻木，员工却只询问疼痛时间。",
            },
        },
        scenario,
        history,
        "我理解您会担心。疼痛从什么时候开始，今天比昨晚更重吗？",
    )
    assert result["feedback"]["level"] == "needs_work", result
    assert "本轮反馈只评价" in result["feedback"]["why"], result
    assert "新情况" in result["feedback"]["issue"], result


def test_complete_safe_closure_is_not_false_critical() -> None:
    scenario = exact_scenario("SCN-CEX-M03-S01")
    result = server.normalize_training_result(
        {
            "customer_reply": "好的，那我现在该怎么办？",
            "feedback": {
                "level": "critical",
                "issue": "员工未停止服务，反而试图在店内分析原因。",
                "why": "顾客有新发麻木，存在延误风险。",
            },
        },
        scenario,
        [{"role": "assistant", "content": scenario["opening"]}],
        "现在先不要继续任何项目，也不要自行判断原因。我会记录情况并上报负责人；如果发麻加重或出现无力，请及时就医或联系急救。",
    )
    assert result["feedback"]["level"] == "good", result
    assert "完整的安全闭环" in result["feedback"]["why"], result


def test_training_suggested_reply_strips_unverified_medical_advice() -> None:
    scenario = exact_scenario("SCN-CEX-M03-S01")
    result = server.normalize_training_result(
        {
            "customer_reply": "我的手还在发麻，怎么办？",
            "feedback": {
                "level": "critical",
                "issue": "危险表达需要立即纠正。",
                "why": "不能继续操作。",
                "suggested_reply": "可能是神经受刺激，不要热敷或按摩，今天停止治疗。",
            },
        },
        scenario,
        [{"role": "assistant", "content": scenario["opening"]}],
        "越痛越有效，今天继续加量。",
    )
    reply = result["feedback"]["suggested_reply"]
    assert "神经受刺激" not in reply and "热敷" not in reply and "按摩" not in reply, result
    assert "我先为您暂停" in reply and "医疗机构评估" in reply, result


def test_mock_multiturn_stays_in_role() -> None:
    employee_turns = ["我不太清楚，应该都差不多吧。", "我错了。", "好的。", "你还想了解什么？"]
    for scenario in server.SCENARIOS:
        history = [{"role": "assistant", "content": scenario["opening"]}]
        replies = []
        for employee in employee_turns:
            response = server.handle_chat({
                "mode": "test",
                "action": "turn",
                "scenario_id": scenario["id"],
                "message": employee,
                "history": history,
                "api_key": "",
            })
            reply = response["result"]["reply"]
            assert_customer_like(reply)
            replies.append(reply)
            history.extend([{"role": "user", "content": employee}, {"role": "assistant", "content": reply}])
            # A clarification request may intentionally repeat until the employee answers the
            # current question; otherwise the customer replies should keep moving forward.
            unique_replies = len(set(replies))
            clarification_repeats = sum("没听明白" in reply or "具体是什么办法" in reply for reply in replies)
            assert unique_replies == len(replies) or clarification_repeats >= 2, {"scenario": scenario["id"], "replies": replies}


def test_static_site_has_same_guardrails() -> None:
    required = [
        "LIMITED_CUSTOMER_POLICY",
        "staticCustomerScenario",
        "staticPublicTrainingScenario",
        "CUSTOMER_ROLE_DRIFT_MARKERS",
        "normalizeStaticCustomerReply",
        "staticCustomerFallback",
        "staticTrainingSafetyDecision",
        "staticTrainingMessageHasCompleteSafeClosure",
        "sanitizeStaticTrainingFutureClaims",
        "sanitizeStaticTrainingSuggestedReply",
        "回答相关性契约",
        "逐项回应",
        "先回应、后追问",
        "customerSystem",
        "coachSystem",
        "Promise.all",
    ]
    assert all(marker in APP_JS for marker in required)
    assert "隐藏场景（不得整段泄露）：${JSON.stringify(staticCustomerScenario(scenario, true))}" in APP_JS
    assert "freeform_current_turn" in APP_JS
    assert "公开场景：${JSON.stringify(staticPublicTrainingScenario(scenario))}" in APP_JS
    assert "隐藏场景（不得泄露）：${JSON.stringify(scenario)}" not in APP_JS
    assert "好，那我先按相近时间复测" in APP_JS


def test_weight_change_conversation_stays_on_question() -> None:
    scenario = exact_scenario("SCN-CEX-M05-S01")
    history = [{"role": "assistant", "content": scenario["opening"]}]

    first = server.handle_chat({
        "mode": "test",
        "action": "turn",
        "scenario_id": scenario["id"],
        "message": "两次体重测量的时间和条件是否一致？",
        "history": history,
        "api_key": "",
    })["result"]["reply"]
    assert "上周早上" in first and "这次晚上" in first, first
    history.extend([{"role": "user", "content": "两次体重测量的时间和条件是否一致？"}, {"role": "assistant", "content": first}])

    second = server.handle_chat({
        "mode": "test",
        "action": "turn",
        "scenario_id": scenario["id"],
        "message": "除了体重之外，最近腰围、体脂或身体围度有没有变化？这几次体重测量的时间和条件是否一致？",
        "history": history,
        "api_key": "",
    })["result"]["reply"]
    assert "腰围" in second and "1厘米" in second, second
    assert "价格" not in second and "设备" not in second, second

    history.extend([{"role": "user", "content": "除了体重之外，最近腰围、体脂或身体围度有没有变化？这几次体重测量的时间和条件是否一致？"}, {"role": "assistant", "content": second}])
    third = server.handle_chat({
        "mode": "test",
        "action": "turn",
        "scenario_id": scenario["id"],
        "message": "单次体重上涨不能直接说明方案没有效果，我们先看连续趋势和测量条件。",
        "history": history,
        "api_key": "",
    })["result"]["reply"]
    assert "效果" in third or "体重" in third, third
    assert "担心担心" not in third, third
    assert "医疗评估" not in third and "方法路由" not in third, third

    history.extend([{"role": "user", "content": "单次体重上涨不能直接说明方案没有效果，我们先看连续趋势和测量条件。"}, {"role": "assistant", "content": third}])
    fourth = server.handle_chat({
        "mode": "test",
        "action": "turn",
        "scenario_id": scenario["id"],
        "message": "那我们先约定三到七天后在相近时间复测，我也会把这几天的饮食、睡眠和运动简单记下来。",
        "history": history,
        "api_key": "",
    })["result"]["reply"]
    assert "复测" in fourth and "记录" in fourth, fourth
    assert "这些专业的我不太懂" not in fourth, fourth


def test_model_generic_reset_is_repaired_after_measurement_explanation() -> None:
    scenario = exact_scenario("SCN-CEX-M05-S01")
    history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": "请问你的体重分别是在什么时候测量的呢？"},
        {"role": "assistant", "content": "上周早上，这次晚上。"},
    ]
    model_like = {
        "reply": "我现在主要还是想先听懂再决定，其他专业的我也不太懂。",
        "emotion": "hesitant",
        "should_continue": True,
    }
    normalized = server.normalize_test_turn_result(
        model_like,
        scenario,
        history,
        "这个测量时间不一样，结果也可能不一样。",
    )
    assert "相近时间" in normalized["reply"], normalized
    assert "先听懂再决定" not in normalized["reply"], normalized


if __name__ == "__main__":
    tests = [
        test_scenario_knowledge_boundaries,
        test_role_drift_is_repaired,
        test_natural_customer_reply_is_preserved,
        test_training_feedback_does_not_penalize_future_fact,
        test_complete_safe_closure_is_not_false_critical,
        test_training_suggested_reply_strips_unverified_medical_advice,
        test_mock_multiturn_stays_in_role,
        test_static_site_has_same_guardrails,
    ]
    results = []
    for test in tests:
        test()
        results.append({"name": test.__name__, "passed": True})
    print(json.dumps({"status": "passed", "tests": results}, ensure_ascii=False))
