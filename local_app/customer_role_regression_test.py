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


def test_scenario_knowledge_boundaries() -> None:
    assert len(server.SCENARIOS) == 30
    for scenario in server.SCENARIOS:
        assert scenario.get("persona", {}).get("knowledge_level"), scenario["id"]
        context = server.customer_turn_context(scenario)
        serialized = json.dumps(context, ensure_ascii=False)
        assert "must_test" not in context
        assert "must_test" not in serialized
        assert not any(rule in serialized for rule in scenario.get("must_test", []))

    beauty = server.scenario_by_id("SCN-QBANK-M08-Q01")
    assert "首次皮肤服务" in beauty["opening"]
    assert "清洁" in beauty["opening"] and "项目选择" in beauty["opening"]


def test_role_drift_is_repaired() -> None:
    scenario = server.scenario_by_id("SCN-QBANK-M08-Q01")
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
    scenario = server.scenario_by_id("SCN-QBANK-M03-Q02")
    natural = "大概有半年了，低头久了会更明显。"
    normalized = server.normalize_test_turn_result({"reply": natural}, scenario, [{"role": "assistant", "content": scenario["opening"]}], "这种情况多久了？")
    assert normalized["reply"] == natural
    assert_customer_like(normalized["reply"])


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
        "CUSTOMER_ROLE_DRIFT_MARKERS",
        "normalizeStaticCustomerReply",
        "staticCustomerFallback",
    ]
    assert all(marker in APP_JS for marker in required)
    assert "隐藏场景（不得泄露）：${JSON.stringify(staticCustomerScenario(scenario))}" in APP_JS
    assert "隐藏场景（不得泄露）：${JSON.stringify(scenario)}" not in APP_JS


if __name__ == "__main__":
    tests = [
        test_scenario_knowledge_boundaries,
        test_role_drift_is_repaired,
        test_natural_customer_reply_is_preserved,
        test_mock_multiturn_stays_in_role,
        test_static_site_has_same_guardrails,
    ]
    results = []
    for test in tests:
        test()
        results.append({"name": test.__name__, "passed": True})
    print(json.dumps({"status": "passed", "tests": results}, ensure_ascii=False))
