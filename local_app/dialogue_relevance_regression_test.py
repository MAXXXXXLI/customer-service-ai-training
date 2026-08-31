"""Regression coverage for current-turn relevance and positive employee voice."""

from __future__ import annotations

import re

import server


def scenario(scenario_id: str) -> dict:
    value = next((item for item in server.SCENARIOS if item.get("id") == scenario_id), None)
    assert value is not None, scenario_id
    return value


def test_short_qa_follow_up_cannot_drift_to_an_old_topic() -> None:
    contextual_query = "点阵波价格是多少 那要多久"
    route = server.route_customer_question(contextual_query)
    result = server.apply_methodology_result(
        {
            "answer": "价格和活动会随城市变化，请告诉我门店。",
            "uncertainties": [],
            "recommended_action": "核对门店。",
        },
        "qa",
        route,
        contextual_query,
        current_message="那要多久？",
    )
    answer = result["answer"]
    assert "需要多久" in answer, result
    assert "价格和活动会随城市变化" not in answer, result


def test_qa_employee_voice_uses_positive_direct_expression_for_normal_turns() -> None:
    route = server.route_customer_question("做一次多久见效")
    result = server.apply_methodology_result(
        {
            "answer": "我不能承诺一次就见效，也不能保证不反弹。",
            "uncertainties": [],
            "recommended_action": "观察变化。",
        },
        "qa",
        route,
        "做一次多久见效",
        current_message="做一次多久见效？",
    )
    answer = result["answer"]
    assert "我会先" in answer, result
    assert not re.search(r"(?<!能)不能|不保证|不承诺|不急着|不把", answer), result


def test_customer_simulator_answers_the_latest_explicit_question_first() -> None:
    base = scenario("SCN-CEX-M03-S02")
    item = {
        **base,
        "id": "SCN-NO-RELEASE-RULES",
        "hidden_information": [],
        "information_release_rules": [],
    }
    history = [{"role": "assistant", "content": "你们这个要多少钱？"}]
    reply = server.normalized_customer_reply(
        "我主要担心点阵波打完更痛。",
        item,
        history,
        "您现在更在意价格还是效果？",
    )
    assert "价格" in reply or "费用" in reply, reply
    assert "更痛" not in reply, reply

    test_reply = server.normalize_test_turn_result(
        {"reply": "我主要担心点阵波打完更痛。"},
        item,
        history,
        "您现在更在意价格还是效果？",
    )["reply"]
    assert "价格" in test_reply or "费用" in test_reply, test_reply


def test_coach_feedback_cannot_jump_from_price_to_pain() -> None:
    item = scenario("SCN-CEX-M02-S01")
    history = [{"role": "assistant", "content": "你们这个太贵了，我为什么要在你们这里做？"}]
    result = server.normalize_training_result(
        {
            "customer_reply": "我主要想知道费用。",
            "feedback": {
                "level": "needs_work",
                "issue": "顾客疼痛时要暂停。",
                "why": "必须先就医。",
                "method_step": "停止服务",
                "knowledge_focus": "疼痛异常",
                "suggested_reply": "我先暂停并建议您就医。",
                "next_goal": "下一轮确认疼痛。",
            },
        },
        item,
        history,
        "我先为您核对价格和活动。",
    )
    feedback = result["feedback"]
    assert feedback["level"] == "needs_work", feedback
    assert re.search(r"价格|费用", feedback["suggested_reply"]), feedback
    assert not re.search(r"疼痛|就医|暂停", " ".join(feedback.values())), feedback


def test_point_wave_default_is_positive_but_red_flag_stop_remains_available() -> None:
    assert "作为需要跟进的异常反应处理" in server.POINT_WAVE_BEST_REPLY
    assert not re.search(r"不把|不急着|(?<!能)不能", server.POINT_WAVE_BEST_REPLY)

    route = server.route_customer_question("我现在胸痛喘不过气怎么办")
    urgent = server.qa_employee_voice_fallback("我现在胸痛喘不过气怎么办", route)
    assert re.search(r"停止|不要继续|急救|医疗机构", urgent), urgent


def test_point_wave_dismissal_coaching_stays_with_the_known_pain_turn() -> None:
    item = scenario("SCN-CEX-M03-S01")
    history = [{"role": "assistant", "content": item["opening"]}]
    result = server.normalize_training_result(
        {
            "customer_reply": "我还没听明白，能再具体说说吗？我主要还是想解决点阵波打完更痛。",
            "feedback": {
                "level": "needs_work",
                "issue": "新客接待要先完成需求分析，再进入项目介绍。",
                "why": "不能只背项目卖点。",
                "method_step": "需求分析",
                "knowledge_focus": "项目知识",
                "suggested_reply": "先做需求分析。",
                "next_goal": "下一轮进入项目介绍。",
            },
        },
        item,
        history,
        "不是",
    )
    feedback = result["feedback"]
    rendered = " ".join(str(value) for value in feedback.values())
    assert "疼痛加重" in rendered, feedback
    assert "暂停后续安排" in feedback["suggested_reply"], feedback
    assert feedback["suggested_reply"] == server.POINT_WAVE_BEST_REPLY, feedback
    assert "需求分析" not in rendered, feedback


def test_point_wave_multiturn_answers_latest_companion_question() -> None:
    item = scenario("SCN-CEX-M03-S01")
    history = [
        {"role": "assistant", "content": "我昨天做完点阵波，今天比原来更痛。你们是不是把我打坏了？"},
        {"role": "user", "content": "我先为您暂停后续安排，并记录疼痛从什么时候开始、现在是否还在加重。"},
        {"role": "assistant", "content": "昨晚开始，今天更重。"},
    ]
    employee = "现在还有麻木、无力或发热吗？"
    customer = server.normalized_customer_reply(
        "我比较怕疼，过程中会不会很难受？", item, history, employee
    )
    assert "怕疼，过程中" not in customer, customer
    assert any(term in customer for term in ("麻木", "无力", "发热", "没留意")), customer
    feedback = server.normalize_training_result(
        {"customer_reply": customer, "feedback": {"level": "good", "suggested_reply": server.POINT_WAVE_BEST_REPLY}},
        item,
        history,
        employee,
    )["feedback"]
    assert "麻木" in feedback["suggested_reply"], feedback
    assert "今天先为您暂停后续安排" in feedback["suggested_reply"], feedback
    assert feedback["suggested_reply"] != server.POINT_WAVE_BEST_REPLY, feedback


def test_assessment_report_drops_an_unseen_topic() -> None:
    history = [
        {"role": "assistant", "content": "你们这个太贵了，我为什么要在你们这里做？"},
        {"role": "user", "content": "我先为您核对城市、门店和项目，再确认当前费用。"},
    ]
    report = server.normalize_assessment_result(
        {
            "dimension_scores": [
                {
                    "id": "D1",
                    "score": 1,
                    "evidence": "员工原话：“我先为您核对城市、门店和项目，再确认当前费用。”",
                    "comment": "顾客疼痛时应先暂停。",
                },
            ],
            "strengths": ["已完成疼痛分流。"],
            "improvements": ["下一轮继续问疼痛程度。"],
            "summary": "本轮重点处理疼痛和就医安排。",
        },
        history,
    )
    rendered = " ".join([
        *(item["comment"] for item in report["dimension_scores"]),
        *report["strengths"],
        *report["improvements"],
        report["summary"],
    ])
    assert not re.search(r"疼痛|就医|暂停", rendered), report


def main() -> None:
    tests = [
        test_short_qa_follow_up_cannot_drift_to_an_old_topic,
        test_qa_employee_voice_uses_positive_direct_expression_for_normal_turns,
        test_customer_simulator_answers_the_latest_explicit_question_first,
        test_coach_feedback_cannot_jump_from_price_to_pain,
        test_point_wave_default_is_positive_but_red_flag_stop_remains_available,
        test_point_wave_dismissal_coaching_stays_with_the_known_pain_turn,
        test_point_wave_multiturn_answers_latest_companion_question,
        test_assessment_report_drops_an_unseen_topic,
    ]
    for test in tests:
        test()
    print("dialogue relevance regression tests passed")


if __name__ == "__main__":
    main()
