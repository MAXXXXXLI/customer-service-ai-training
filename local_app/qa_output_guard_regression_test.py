"""Regression coverage for preserving grounded online QA explanations.

The final QA guard must remove internal process language and unsupported
promises, but it must not turn an in-scope project explanation into the generic
"what would you like to know" response merely because it includes one boundary.
"""

from __future__ import annotations

import json

import server


POINT_WAVE_ANSWER = (
    "点阵波以局部重复机械刺激为主，体验中可能感觉到敲击、振动或酸胀。"
    "它不是医疗治疗，也不能保证固定效果。"
)


def test_grounded_project_explanation_survives_final_voice_guard() -> None:
    question = "点阵波的原理是什么？"
    route = server.route_customer_question(question)
    result = server.apply_methodology_result(
        {"answer": POINT_WAVE_ANSWER, "uncertainties": [], "recommended_action": ""},
        "qa",
        route,
        question,
        current_message=question,
    )
    assert result["answer"] == POINT_WAVE_ANSWER, result
    assert not server.qa_answer_needs_employee_voice_repair(POINT_WAVE_ANSWER)
    assert not server.employee_voice_needs_positive_repair(
        POINT_WAVE_ANSWER,
        question,
        route,
        preserve_substantive_qa_explanation=True,
    )


def test_online_model_path_keeps_grounded_project_explanation() -> None:
    original_mock = server.MOCK_MODE
    original_call_model = server.call_model

    def fake_call_model(system: str, *_: object, **__: object) -> tuple[str, dict]:
        # Skip the optional FAQ selector so this exercises the regular online
        # model -> safety -> final QA guard path.
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            return json.dumps({"match_id": "NONE", "confidence": 0.0, "answer": ""}), {}
        return json.dumps({"answer": POINT_WAVE_ANSWER, "uncertainties": [], "recommended_action": ""}, ensure_ascii=False), {
            "model": "test-model"
        }

    server.MOCK_MODE = False
    server.call_model = fake_call_model
    try:
        response = server.handle_chat({
            "mode": "qa",
            "action": "turn",
            "message": "点阵波的原理是什么？",
            "history": [],
            "api_key": "regression-key",
            "model": "Qwen/Qwen3.5-35B-A3B",
        })
    finally:
        server.MOCK_MODE = original_mock
        server.call_model = original_call_model

    assert response["meta"]["mock"] is False, response
    assert response["result"]["answer"] == POINT_WAVE_ANSWER, response


def test_bare_refusal_and_internal_process_voice_are_still_repaired() -> None:
    effectiveness_question = "做一次多久见效？"
    effectiveness_route = server.route_customer_question(effectiveness_question)
    bare_refusal = "我不能承诺一次就见效，也不能保证不反弹。"
    result = server.apply_methodology_result(
        {"answer": bare_refusal, "uncertainties": [], "recommended_action": ""},
        "qa",
        effectiveness_route,
        effectiveness_question,
        current_message=effectiveness_question,
    )
    assert result["answer"] != bare_refusal, result
    assert "不承诺" not in result["answer"] and "不保证" not in result["answer"], result

    project_question = "点阵波的原理是什么？"
    project_route = server.route_customer_question(project_question)
    internal = "当前应按SOP完成确认，门店不能直接判断，并按异常流程处理。"
    repaired = server.apply_methodology_result(
        {"answer": internal, "uncertainties": [], "recommended_action": ""},
        "qa",
        project_route,
        project_question,
        current_message=project_question,
    )
    assert repaired["answer"] != internal, repaired
    assert "SOP" not in repaired["answer"] and "异常流程" not in repaired["answer"], repaired


def main() -> None:
    tests = [
        test_grounded_project_explanation_survives_final_voice_guard,
        test_online_model_path_keeps_grounded_project_explanation,
        test_bare_refusal_and_internal_process_voice_are_still_repaired,
    ]
    for test in tests:
        test()
    print(json.dumps({"status": "passed", "tests": [test.__name__ for test in tests]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
