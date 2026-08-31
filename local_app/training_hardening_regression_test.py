"""Focused regression coverage for training and assessment safety hardening."""

from __future__ import annotations

import re

import server


def scenario(scenario_id: str) -> dict:
    return next(item for item in server.SCENARIOS if item.get("id") == scenario_id)


def test_strong_pain_requires_pause_before_any_energy_change() -> None:
    item = scenario("SCN-CEX-M03-S02")
    history = [{"role": "assistant", "content": item["opening"]}]

    lowered = server.normalize_training_result(
        {"customer_reply": "无关回复", "feedback": {"level": "good", "suggested_reply": "可以调低能量再试。"}},
        item,
        history,
        "我先把能量调低一些。",
    )
    assert lowered["feedback"]["level"] == "needs_work", lowered
    assert lowered["feedback"]["suggested_reply"] == server.POINT_WAVE_IN_SESSION_PAUSE_REPLY, lowered
    assert lowered["customer_reply"] == "我已经很痛了，能不能先停下来？", lowered

    continued = server.normalize_training_result(
        {"customer_reply": "无关回复", "feedback": {"level": "good", "suggested_reply": "继续感受一下。"}},
        item,
        history,
        "我把能量调低一些，您再继续感受一下。",
    )
    assert continued["feedback"]["level"] == "critical", continued
    assert continued["feedback"]["suggested_reply"] == server.POINT_WAVE_IN_SESSION_PAUSE_REPLY, continued
    assert continued["customer_reply"] == "我已经很痛了，能不能先停下来？", continued


def test_suggested_reply_is_relevant_for_every_feedback_level() -> None:
    price = scenario("SCN-CEX-M02-S01")
    price_history = [{"role": "assistant", "content": price["opening"]}]
    for level in ("needs_work", "critical"):
        normalized = server.normalize_training_result(
            {"customer_reply": "无关回复", "feedback": {"level": level, "suggested_reply": "现在先暂停，回家观察。"}},
            price,
            price_history,
            "我需要再确认。",
        )
        assert re.search(r"价格|费用", normalized["feedback"]["suggested_reply"]), normalized

    safety = scenario("SCN-CEX-M03-S02")
    safety_history = [{"role": "assistant", "content": safety["opening"]}]
    normalized = server.normalize_training_result(
        {"customer_reply": "无关回复", "feedback": {"level": "needs_work", "suggested_reply": "价格请以门店核对为准。"}},
        safety,
        safety_history,
        "我先把能量调低一些。",
    )
    assert normalized["feedback"]["suggested_reply"] == server.POINT_WAVE_IN_SESSION_PAUSE_REPLY, normalized


def test_assessment_blocks_recovery_advice_caps_unclosed_red_flag_and_rejects_unknown_scene() -> None:
    red_flag_history = [
        {"role": "assistant", "content": "我现在胸痛、呼吸困难。"},
        {"role": "user", "content": "不需要医疗评估，先在家观察48小时。"},
    ]
    details = server.detect_assessment_failure_details(red_flag_history)
    assert "CF-01" in details, details
    assert server.assessment_red_flag_without_complete_safe_closure(red_flag_history)

    for message in ("不建议去急诊，先观察。", "无需急诊。", "先别去医院，观察一晚。", "不建议做医疗评估。", "现在不急着就医。"):
        details = server.detect_assessment_failure_details([
            {"role": "assistant", "content": "我现在胸痛、呼吸困难。"},
            {"role": "user", "content": message},
        ])
        assert "CF-01" in details, (message, details)

    delayed = "我理解您很担心，先了解一下不舒服多久了；但为了安全，我不能判断原因。您先回家睡一觉，明天再说。"
    delayed_history = [
        {"role": "assistant", "content": "我现在胸痛，还有点喘不过气。"},
        {"role": "user", "content": delayed},
    ]
    assert server.training_critical_reason(delayed, delayed_history), "red-flag delay to tomorrow must be critical in training"
    assert "CF-01" in server.detect_assessment_failure_details(delayed_history), "red-flag delay to tomorrow must be CF-01"

    diagnosis = "你这是颈椎病，先给你安排几个治疗项目。"
    assert server.unsafe_claim_hits(diagnosis), "direct disease diagnosis must be a high-risk training claim"
    assert not server.unsafe_claim_hits("您不是颈椎病，门店不能诊断。"), "a diagnostic boundary must not be treated as a diagnosis"
    diagnosis_history = [
        {"role": "assistant", "content": "我肩颈持续疼，转头受限，很担心。"},
        {"role": "user", "content": diagnosis},
    ]
    assert server.training_critical_reason(diagnosis, diagnosis_history), "direct diagnosis must be critical in training"
    assert "CF-02" in server.detect_assessment_failure_details(diagnosis_history), "direct diagnosis must be CF-02"

    discomfort_history = [{"role": "assistant", "content": "我做完项目后很疼，能不能先停？"}]
    for unsafe_recovery in (
        "建议回家热敷。",
        "先冰敷观察48小时。",
        "建议先回去休息两天。",
        "先忍一忍，继续做完。",
    ):
        assert server.training_critical_reason(unsafe_recovery, discomfort_history), (
            "known post-service discomfort must not receive unverified self-treatment or continuation",
            unsafe_recovery,
        )
        details = server.detect_assessment_failure_details(
            [*discomfort_history, {"role": "user", "content": unsafe_recovery}]
        )
        assert "CF-04" in details, (unsafe_recovery, details)

    report = server.normalize_assessment_result(
        {
            "dimension_scores": [
                {"id": "D6", "score": 15, "evidence": "员工原话：“不需要医疗评估，先在家观察48小时。”", "comment": "建议回家热敷、按摩，观察48小时。"},
            ],
            "critical_failures": [],
            "strengths": ["可以先冰敷后在家观察。"],
            "improvements": ["先回家休息观察两天，再决定是否联系门店。"],
            "next_training_scene": "SCN-UNKNOWN",
            "summary": "本轮没有关键失败，但分数封顶59分；建议自行处理。",
        },
        red_flag_history,
    )
    assert report["critical_failures"] and report["critical_failures"][0]["code"] == "CF-01", report
    assert report["critical_failures"][0]["score_cap"] == 59, report
    d6 = next(item for item in report["dimension_scores"] if item["id"] == "D6")
    assert d6["score"] <= 6, report
    rendered = repr({
        "comments": [item["comment"] for item in report["dimension_scores"]],
        "strengths": report["strengths"],
        "improvements": report["improvements"],
        "summary": report["summary"],
    })
    assert not re.search(r"热敷|按摩|冰敷|观察48小时|观察两天|封顶59", rendered), report
    assert report["next_training_scene"] in {item["id"] for item in server.SCENARIOS}, report

    no_failure = server.normalize_assessment_result(
        {"dimension_scores": [], "critical_failures": [], "summary": "本轮出现关键失败，分数封顶59分。"},
        [],
    )
    assert no_failure["summary"] == server.ASSESSMENT_SUMMARY_BOUNDARY, no_failure


if __name__ == "__main__":
    test_strong_pain_requires_pause_before_any_energy_change()
    test_suggested_reply_is_relevant_for_every_feedback_level()
    test_assessment_blocks_recovery_advice_caps_unclosed_red_flag_and_rejects_unknown_scene()
    print("training hardening regression tests passed")
