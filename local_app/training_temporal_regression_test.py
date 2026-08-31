from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

import server


ROOT = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT / "local_app" / "static" / "app.js"
SCENARIO_ID = "SCN-CEX-M03-S01"
FEEDBACK_KEYS = {
    "level",
    "issue",
    "why",
    "method_step",
    "knowledge_focus",
    "suggested_reply",
    "next_goal",
}


def exact_scenario() -> dict[str, Any]:
    scenario = next((item for item in server.SCENARIOS if item.get("id") == SCENARIO_ID), None)
    assert scenario is not None, f"测试场景不存在：{SCENARIO_ID}"
    return scenario


def base_feedback(**overrides: str) -> dict[str, str]:
    feedback = {
        "level": "needs_work",
        "issue": "这一轮还需要更准确地承接顾客当前的担心。",
        "why": "只根据本轮回答前已经出现的对话评价。",
        "method_step": "承接担心并完成必要问询",
        "knowledge_focus": "服务后变化与安全边界",
        "suggested_reply": "我理解您会担心，先说说疼痛从什么时候开始、现在是否在加重。",
        "next_goal": "下一轮只补一个必要的安全问题。",
    }
    feedback.update(overrides)
    return feedback


def normalize(
    employee_message: str,
    history: list[dict[str, str]],
    *,
    customer_reply: str = "我还是有点担心，想先弄清楚。",
    feedback: dict[str, str] | None = None,
) -> dict[str, Any]:
    return server.normalize_training_result(
        {
            "customer_reply": customer_reply,
            "feedback": feedback or base_feedback(),
        },
        exact_scenario(),
        history,
        employee_message,
    )


def feedback_text(result: dict[str, Any]) -> str:
    feedback = result.get("feedback") or {}
    return " ".join(str(feedback.get(key, "")) for key in sorted(FEEDBACK_KEYS))


UNRELEASED_HAND_FACT_ASSERTION = re.compile(
    r"(?:顾客|您).{0,24}(?:已经|明确|刚刚?|表示|提到|出现|伴随|新发|有).{0,20}"
    r"(?:手麻|手臂.{0,4}(?:发麻|麻木)|新发麻木)|"
    r"(?:未|没有|漏掉|忽略).{0,8}(?:识别|处理|承接)?.{0,12}"
    r"(?:手麻|手臂.{0,4}(?:发麻|麻木)|新发麻木)",
    re.I,
)


def assert_no_unreleased_hand_fact(result: dict[str, Any]) -> None:
    text = feedback_text(result)
    assert not UNRELEASED_HAND_FACT_ASSERTION.search(text), text


def test_point_wave_approved_reply_is_good_without_future_fact() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee = server.POINT_WAVE_BEST_REPLY
    leaked_feedback = base_feedback(
        level="critical",
        issue="员工未识别顾客已经出现的手臂发麻。",
        why="顾客刚刚表示手麻，不能再说这是正常现象。",
    )
    result = normalize(
        employee,
        history,
        customer_reply="昨晚开始疼，今天比昨晚更重，而且手臂新发麻木。",
        feedback=leaked_feedback,
    )
    assert result["feedback"]["level"] == "good", result
    assert_no_unreleased_hand_fact(result)
    assert result["feedback"]["suggested_reply"] == server.POINT_WAVE_BEST_REPLY, result
    assert "点阵波" in result["feedback"]["knowledge_focus"], result


def test_retired_point_wave_normalization_script_is_critical() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    retired = (
        "请不用担心，这是正常反应。点阵波造成微损伤后会自我修复，"
        "痛则不通，第二天之后就会消失。"
    )
    result = normalize(
        retired,
        history,
        feedback=base_feedback(level="good", issue="模型误判为历史最佳话术。"),
    )
    assert result["feedback"]["level"] == "critical", result
    assert result["feedback"]["suggested_reply"] != retired, result


def test_screenshot_two_dismissal_is_critical_without_future_fact() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    leaked_feedback = base_feedback(
        level="critical",
        issue="顾客提到了新发手麻，员工却没有识别手麻。",
        why="顾客已经明确表达手臂麻木，属于需要处理的红旗。",
    )
    result = normalize(
        "不是的这没啥问题",
        history,
        customer_reply="我还没听明白，能再具体说明吗？我主要还是想解决点阵波打完更痛。",
        feedback=leaked_feedback,
    )
    assert result["feedback"]["level"] == "critical", result
    assert_no_unreleased_hand_fact(result)
    assert re.search(r"没啥问题|否定|轻率|正常", feedback_text(result)), result


def test_safe_pause_and_change_question_is_not_misread_as_continuing_service() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee = (
        "我理解您会担心。疼痛比原来加重不能先说是正常，今天先暂停后续安排；"
        "我先确认从什么时候开始、今天是否比昨晚更重？"
    )
    result = normalize(
        employee,
        history,
        customer_reply="昨晚开始疼，今天比昨晚更重一点。",
        feedback=base_feedback(level="good", issue="先暂停并询问变化，处理方向正确。"),
    )
    assert result["feedback"]["level"] == "good", result
    assert "继续、忍耐或加量" not in feedback_text(result), result

    follow_up_history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": employee},
        {"role": "assistant", "content": "昨晚开始疼，今天比昨晚更重了一点。"},
    ]
    companion = normalize(
        "除了疼痛加重，还有没有手麻、无力、发热或红肿？",
        follow_up_history,
        customer_reply="我的手臂是今天才开始发麻的。",
        feedback=base_feedback(level="good", issue="模型反馈不应覆盖安全问询。"),
    )
    assert companion["feedback"]["level"] == "good", companion
    assert "伴随" in feedback_text(companion) or "麻木" in feedback_text(companion), companion

    no_pause = normalize(
        "除了疼痛加重，还有没有手麻、无力、发热或红肿？",
        [{"role": "assistant", "content": scenario["opening"]}],
        customer_reply="我的手臂是今天才开始发麻的。",
        feedback=base_feedback(level="good"),
    )
    assert no_pause["feedback"]["level"] == "needs_work", no_pause


def test_known_red_flag_has_three_distinct_safety_levels() -> None:
    scenario = exact_scenario()
    known_history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": "这种情况从什么时候开始？有没有其他新的不适？"},
        # 使用释放闸门实际会生成的规范化短句，确保上一轮输出
        # 能被下一轮安全状态直接识别，不只测试原始题干长句。
        {"role": "assistant", "content": "昨晚开始疼，今天更重。手臂新麻了。"},
    ]

    partial = normalize(
        "这个需要重视，建议您就医并且检查。",
        known_history,
        feedback=base_feedback(level="critical", issue="安全闭环不足。"),
    )
    assert partial["feedback"]["level"] == "needs_work", partial

    complete = normalize(
        "今天先暂停所有项目，我们不在店内判断原因。"
        "我会立即记录情况并上报负责人，建议您尽快去医疗机构检查评估。",
        known_history,
        feedback=base_feedback(level="critical", issue="模型误判为关键失败。"),
    )
    assert complete["feedback"]["level"] == "good", complete

    dangerous = normalize(
        "这是正常的，没关系，今天可以继续做并且加量。",
        known_history,
        feedback=base_feedback(level="good", issue="模型误判为可通过。"),
    )
    assert dangerous["feedback"]["level"] == "critical", dangerous

    standard_reply_after_red_flag = normalize(
        server.POINT_WAVE_BEST_REPLY,
        known_history,
        feedback=base_feedback(level="good", issue="模型忽略了已知红旗。"),
    )
    assert standard_reply_after_red_flag["feedback"]["level"] == "needs_work", standard_reply_after_red_flag

    contradictory = normalize(
        "先暂停并上报记录，我们不在店内判断原因，建议您就医；"
        "但这也是正常反应，明天可以继续做。",
        known_history,
        customer_reply="我听着还是不放心。",
        feedback=base_feedback(level="good", issue="模型被安全关键词误导。"),
    )
    assert contradictory["feedback"]["level"] == "critical", contradictory
    assert not server.training_message_has_complete_safe_closure(
        "先暂停、记录并上报，我们不在店内判断原因，建议就医；"
        "但这是正常反应，明天继续做。"
    )

    chest_pain_history = [{"role": "assistant", "content": "我现在胸痛，呼吸也不太舒服。"}]
    chest_pain = server.normalize_training_result(
        {
            "customer_reply": "我还是不放心。",
            "feedback": base_feedback(level="good", issue="模型误判为安全。"),
        },
        None,
        chest_pain_history,
        "这是正常的，不用太担心。",
    )
    assert chest_pain["feedback"]["level"] == "critical", chest_pain


def test_employee_hypothesis_does_not_become_a_customer_fact() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    result = normalize(
        "如果手臂发麻的话需要重视，建议尽快就医检查。",
        history,
        customer_reply="我就是比昨天更痛，其他的还没说。",
        feedback=base_feedback(
            level="critical",
            issue="顾客已经提到手麻，员工没有完成停止流程。",
            why="顾客出现手臂麻木后必须立即处理。",
        ),
    )
    assert_no_unreleased_hand_fact(result)


def test_current_customer_reply_never_changes_current_feedback() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    employee = "我先确认一下您现在最担心的是什么。"
    coach_feedback = base_feedback(
        level="good",
        issue="这一轮先承接了顾客已经说出的担心。",
        why="评分只依据员工说话前已经公开的信息。",
    )
    ordinary = normalize(employee, history, customer_reply="我还是有点担心。", feedback=coach_feedback)
    newly_revealed = normalize(
        employee,
        history,
        customer_reply="我的手臂今天开始麻木。",
        feedback=coach_feedback,
    )
    assert ordinary["feedback"] == newly_revealed["feedback"], (ordinary, newly_revealed)


def test_questions_negations_and_denied_safety_actions_are_distinguished() -> None:
    red_flag_history = [{"role": "assistant", "content": "我现在胸痛，手臂也开始发麻。"}]

    for employee in (
        "您是不是还想继续做？",
        "我不会把它当成正常现象，也不会继续做。",
        "我不认为这是正常现象，今天先暂停。",
        "继续做的话会不会让情况变得更加严重呢？",
        "我不把这说成正常反应，今天先暂停。",
        "这不算正常反应，今天先暂停。",
        "不是让您继续做，我们今天先暂停。",
        "难道这是正常反应？今天先暂停。",
        "难道还能继续做？我们今天先暂停。",
        "是否正常还不能判断，今天先暂停。",
        "不一定可以做，先暂停。",
        "绝不意味着可以继续做。",
    ):
        assert server.training_critical_reason(employee, red_flag_history) == "", employee
        failures = server.detect_assessment_failures(red_flag_history + [{"role": "user", "content": employee}])
        assert "CF-01" not in failures and "CF-04" not in failures, (employee, failures)

    for employee in (
        "我们提供的不是医疗治疗，不会治疗疾病。",
        "具体剂量必须由医生决定，门店不能建议。",
    ):
        assert not server.unsafe_claim_hits(employee), employee
        assert server.training_critical_reason(employee, red_flag_history) == "", employee
        assert "CF-02" not in server.detect_assessment_failures(
            red_flag_history + [{"role": "user", "content": employee}]
        ), employee

    for employee in (
        "不用停，接着做完",
        "不用停，照常操作",
        "今天还是把项目做完吧",
        "没必要暂停，做完再说",
        "明天还可以做",
        "如果缓解，明天可以做",
        "没问题",
        "没啥问题",
        "没什么问题",
        "不要紧",
        "不碍事",
        "不能判断原因但明天还可以做",
    ):
        assert server.training_safe_response_state(employee, red_flag_history) == "critical", employee
        failures = server.detect_assessment_failures(red_flag_history + [{"role": "user", "content": employee}])
        assert "CF-01" in failures and "CF-04" in failures, (employee, failures)

    point_wave_history = [{"role": "assistant", "content": exact_scenario()["opening"]}]
    assert server.training_critical_reason(
        "这不代表之后会缓解，今天先暂停后续项目。",
        point_wave_history,
        exact_scenario(),
    ) == ""

    incomplete = normalize(
        "我不会记录也不会上报负责人，但建议您就医。",
        red_flag_history,
        feedback=base_feedback(level="good"),
    )
    assert incomplete["feedback"]["level"] == "critical", incomplete

    refusal = normalize(
        "不用暂停，别记录或上报，更不建议就医。",
        red_flag_history,
        customer_reply="好的，我会尽快去检查。",
        feedback=base_feedback(level="good"),
    )
    assert refusal["feedback"]["level"] == "critical", refusal
    assert "尽快去检查" not in refusal["customer_reply"], refusal


def test_symptom_negation_is_clause_aware() -> None:
    negated = server.NEGATED_RED_FLAG_PATTERN.sub(" ", "我没手麻，也没胸痛，只想问价格。")
    assert not server.TRAINING_RED_FLAG_PATTERN.search(negated), negated
    assert server.training_safe_response_state(
        "好的，我先帮您核对价格。",
        [{"role": "assistant", "content": "我没手麻，也没胸痛，只想问价格。"}],
    ) == "none"

    mixed = server.NEGATED_RED_FLAG_PATTERN.sub(" ", "我没有胸痛但手麻越来越重。")
    assert "胸痛" not in mixed and "手麻" in mixed, mixed
    assert server.TRAINING_RED_FLAG_PATTERN.search(mixed), mixed

    for sentence in ("没有手臂发麻", "没有任何胸痛", "无胸痛"):
        affirmed = server.NEGATED_RED_FLAG_PATTERN.sub(" ", sentence)
        assert not server.TRAINING_RED_FLAG_PATTERN.search(affirmed), (sentence, affirmed)

    affirmed_weakness = server.NEGATED_RED_FLAG_PATTERN.sub(" ", "无力越来越明显")
    assert server.TRAINING_RED_FLAG_PATTERN.search(affirmed_weakness), affirmed_weakness


def test_finish_failure_detection_respects_turn_order_and_negation() -> None:
    future_red_flag = [
        {"role": "assistant", "content": "我想今天体验一下。"},
        {"role": "user", "content": "没问题，可以做，我给您安排。"},
        {"role": "assistant", "content": "但我现在突然有些胸痛。"},
    ]
    assert "CF-01" not in server.detect_assessment_failures(future_red_flag)

    failure_then_repair = [
        {"role": "assistant", "content": "我现在突然胸痛，呼吸也不太舒服。"},
        {"role": "user", "content": "没事，这是正常现象，我们继续做。"},
        {"role": "assistant", "content": "还是很不舒服。"},
        {"role": "user", "content": "那现在立即停止，我联系负责人并建议您尽快就医。"},
    ]
    assert "CF-01" in server.detect_assessment_failures(failure_then_repair)

    negated_red_flag = [
        {"role": "assistant", "content": "我没有胸痛，也没有呼吸困难或晕厥。"},
        {"role": "user", "content": "好的，在确认其他情况后可以安排体验。"},
    ]
    assert "CF-01" not in server.detect_assessment_failures(negated_red_flag)

    contradictory = [
        {"role": "assistant", "content": "我现在手臂发麻，而且越来越重。"},
        {"role": "user", "content": "今天先暂停；如果缓解，明天可以继续做。"},
    ]
    failures = server.detect_assessment_failures(contradictory)
    assert "CF-01" in failures and "CF-04" in failures, failures

    grounded_report = server.normalize_assessment_result(
        {
            "dimension_scores": [
                {
                    "id": "D1",
                    "score": 8,
                    "evidence": "员工原话：我已经暂停并上报负责人。",
                    "comment": "完成了安全处置。",
                }
            ]
        },
        [{"role": "user", "content": "我先了解一下您的情况。"}],
    )
    by_dimension = {item["id"]: item for item in grounded_report["dimension_scores"]}
    assert by_dimension["D1"]["score"] == 0 and by_dimension["D1"]["evidence"] == "对话中未体现", grounded_report
    assert "我先了解一下您的情况" in by_dimension["D2"]["evidence"], grounded_report


def test_medical_claim_rules_match_server_and_static_expectations() -> None:
    assert server.unsafe_claim_hits("这个项目可以治疗糖尿病。")
    assert server.unsafe_claim_hits("这个项目可以治疗 糖尿病。")
    assert server.unsafe_claim_hits("这种情况可能涉及神经损伤。")
    assert server.unsafe_claim_hits("门店不能判断原因但这个项目可以治疗疾病。")
    assert not server.unsafe_claim_hits("这个项目不可以治疗糖尿病。")
    assert not server.unsafe_claim_hits("这种情况是否可能涉及神经损伤？")
    assert not server.unsafe_claim_hits("我们提供的不是医疗治疗，不会治疗疾病。")
    assert not server.unsafe_claim_hits("具体剂量必须由医生决定，门店不能建议。")


def test_real_training_calls_are_isolated_and_schema_compatible() -> None:
    scenario = exact_scenario()
    history = [{"role": "assistant", "content": scenario["opening"]}]
    current_reply = "昨晚八点左右开始，现在确实更明显。"
    records: list[dict[str, Any]] = []
    records_lock = threading.Lock()

    original_call_model = server.call_model
    original_mock_mode = server.MOCK_MODE

    def fake_call_model(
        system: str,
        messages: list[dict[str, str]],
        model: str,
        api_key: str,
        temperature: float = 0.4,
        max_tokens: int = 1800,
    ) -> tuple[str, dict[str, Any]]:
        serialized = json.dumps({"system": system, "messages": messages}, ensure_ascii=False)
        # The serialized request escapes quotes inside the system prompt; use
        # the unique mode marker rather than depending on JSON escaping.
        customer_call = "freeform_current_turn" in serialized
        with records_lock:
            records.append({
                "role": "customer" if customer_call else "coach",
                "system": system,
                "messages": messages,
                "serialized": serialized,
            })
        if customer_call:
            return (
                json.dumps({"customer_reply": current_reply}, ensure_ascii=False),
                {"model": model, "usage": {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}},
            )
        return (
            json.dumps({"feedback": base_feedback(level="needs_work")}, ensure_ascii=False),
            {"model": model, "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12}},
        )

    server.call_model = fake_call_model
    server.MOCK_MODE = False
    try:
        response = server.handle_chat({
            "mode": "training",
            "action": "turn",
            "scenario_id": scenario["id"],
            "message": "我理解您更痛会担心。疼痛从什么时候开始，今天是否比昨晚更重？",
            "history": history,
            "api_key": "unit-test-key",
            "model": server.AVAILABLE_MODELS[0]["id"],
        })
    finally:
        server.call_model = original_call_model
        server.MOCK_MODE = original_mock_mode

    assert len(records) == 2, records
    by_role = {record["role"]: record for record in records}
    assert set(by_role) == {"customer", "coach"}, records
    customer_prompt = by_role["customer"]["serialized"]
    coach_prompt = by_role["coach"]["serialized"]

    assert "freeform_current_turn" in customer_prompt
    assert not any(str(fact) in customer_prompt for fact in scenario.get("hidden_information", []))
    for forbidden_key in ("hidden_information", "information_release_rules", "reference_answer", "must_test"):
        assert forbidden_key not in coach_prompt, {"field": forbidden_key, "coach_prompt": coach_prompt}
    for field in ("hidden_information", "information_release_rules"):
        for hidden_value in scenario.get(field, []):
            assert str(hidden_value) not in coach_prompt, {"value": hidden_value, "coach_prompt": coach_prompt}
    assert str(scenario.get("reference_answer", "")) not in coach_prompt
    assert current_reply not in coach_prompt
    assert scenario["opening"] in coach_prompt and scenario["task"] in coach_prompt

    assert response["ok"] is True and response["mode"] == "training", response
    released_reply = response["result"]["customer_reply"]
    assert "昨晚" in released_reply and re.search(r"更重|更明显", released_reply), response
    assert not re.search(r"手麻|发麻|麻木", released_reply), response
    assert FEEDBACK_KEYS <= set(response["result"]["feedback"]), response
    assert response.get("citations") == [] and response.get("retrieved") == [], response
    meta = response.get("meta") or {}
    assert meta.get("mock") is False and meta.get("calls") == 2, meta
    assert set(meta.get("roles") or []) == {"customer", "feedback"}, meta
    assert meta.get("usage", {}).get("prompt_tokens") == 18, meta
    assert meta.get("usage", {}).get("completion_tokens") == 8, meta
    assert meta.get("usage", {}).get("total_tokens") == 26, meta


def test_static_training_prompts_and_finish_context_are_isolated() -> None:
    app_js = APP_JS_PATH.read_text(encoding="utf-8")
    prompt_defaults = (APP_JS_PATH.parent / "data" / "prompt_defaults.json").read_text(encoding="utf-8")
    assert "function staticPublicTrainingScenario" in app_js
    assert "staticTrainingSafetyDecision" in app_js
    assert "staticTrainingMessageHasUnsafeContradiction" in app_js
    assert re.search(r"\b(?:const|let)\s+customerSystem\s*=", app_js)
    assert re.search(r"\b(?:const|let)\s+coachSystem\s*=", app_js)
    assert re.search(
        r"Promise\.allSettled\(\[\s*callStaticModel\(customerSystem[\s\S]{0,1800}?callStaticModel\(coachSystem",
        app_js,
    ), "training 静态分支没有并行调用隔离的 customer/coach prompts"

    public_context_call = "JSON.stringify(staticPublicTrainingScenario(scenario))"
    assert app_js.count(public_context_call) >= 2, "coach 与 finish 都应只使用公开场景字段"
    assert "场景：${JSON.stringify(scenario)}" not in app_js
    finish_prompt = app_js + prompt_defaults
    assert "一句员工原话只能使用它之前已出现的顾客信息" in finish_prompt
    assert "后来顾客才透露的信息不得追溯扣分" in finish_prompt
    assert "后续的正确补救不能抹去先前已经发生的关键失败" in finish_prompt
    assert "顾客明确说“没有/否认”的症状不得当作已出现" in finish_prompt

    helper_match = re.search(
        r"function staticPublicTrainingScenario\(scenario\s*=\s*\{\}\)\s*\{([\s\S]{0,1200}?)\n\}",
        app_js,
    )
    assert helper_match, "未找到公开场景边界 helper"
    helper_body = helper_match.group(1)
    for allowed in ("title", "module_title", "task", "opening"):
        assert allowed in helper_body, helper_body
    for forbidden in ("hidden_information", "information_release_rules", "reference_answer", "must_test"):
        assert forbidden not in helper_body, helper_body
    assert "staticTrainingMessageDeniesSafetyAction" in app_js
    assert "staticTrainingSafeActionFlags" in app_js
    assert "const unsafeContinuation = staticHasAffirmativeEmployeeMatch(message, continuePattern)" in app_js
    assert "治疗|治好|根治|改善糖尿病" in app_js


def test_point_wave_natural_continuity_and_role_attribution_are_grounded() -> None:
    scenario = next(item for item in server.SCENARIOS if item.get("id") == "SCN-CEX-M03-S02")
    history = [
        {"role": "assistant", "content": scenario["opening"]},
        {"role": "user", "content": "您不用继续忍，我们先停止操作。"},
        {"role": "assistant", "content": "我已经很痛了，能不能先停下来？"},
        {"role": "user", "content": "现在疼痛大概是几分？"},
        {"role": "assistant", "content": "大概8分。"},
        {"role": "user", "content": "现在有没有麻木、无力、肿胀或发热？"},
        {"role": "assistant", "content": "我比较怕疼，过程中会不会很难受？"},
    ]
    employee = "我们已经停止今天的操作。我会记录本次部位和反应，并请负责人马上复核；如果持续加重，建议尽快由医疗机构评估。"
    normalized = server.normalize_training_result(
        {
            "customer_reply": "我现在主要还是想尽快处理，其他专业的我也不太懂。",
            "feedback": {
                **base_feedback(level="good"),
                "issue": "员工主动询问‘过程中会不会很难受’，没有执行安全流程。",
                "why": "员工在顾客8分疼痛后仍询问‘过程中会不会很难受’。",
            },
        },
        scenario,
        history,
        employee,
    )
    assert normalized["customer_reply"].startswith("好，那今天就先不做了"), normalized
    assert normalized["feedback"]["level"] == "good", normalized
    assert "过程中会不会很难受" not in normalized["feedback"]["issue"], normalized
    assert "终止本次操作" in normalized["feedback"]["issue"], normalized

    failures = server.detect_assessment_failures([
        {"role": "assistant", "content": "现在疼痛大概8分。"},
        {"role": "user", "content": "收到，我们今天不再继续操作，我先确认有没有麻木或无力。"},
    ])
    assert "CF-04" not in failures, failures
    assert server.training_critical_reason(
        "收到，我们今天不再继续操作，我先确认有没有麻木或无力。",
        [{"role": "assistant", "content": "现在疼痛大概8分。"}],
        scenario,
    ) == ""
    grounded = server.deterministic_training_feedback(
        "收到，我们今天不再继续操作，我先确认有没有麻木、无力、肿胀、发热或继续加重。",
        [{"role": "assistant", "content": "现在疼痛大概8分。"}],
        scenario,
    )
    assert grounded and grounded["level"] == "good", grounded
    assert "CUSTOMER_REALISM_POLICY" in APP_JS_PATH.read_text(encoding="utf-8")
    assert "不按轮次机械轮播隐藏异议" in server.TRAIN_CUSTOMER_SYSTEM


if __name__ == "__main__":
    tests = [
        test_point_wave_approved_reply_is_good_without_future_fact,
        test_retired_point_wave_normalization_script_is_critical,
        test_screenshot_two_dismissal_is_critical_without_future_fact,
        test_safe_pause_and_change_question_is_not_misread_as_continuing_service,
        test_known_red_flag_has_three_distinct_safety_levels,
        test_employee_hypothesis_does_not_become_a_customer_fact,
        test_current_customer_reply_never_changes_current_feedback,
        test_questions_negations_and_denied_safety_actions_are_distinguished,
        test_symptom_negation_is_clause_aware,
        test_finish_failure_detection_respects_turn_order_and_negation,
        test_medical_claim_rules_match_server_and_static_expectations,
        test_real_training_calls_are_isolated_and_schema_compatible,
        test_static_training_prompts_and_finish_context_are_isolated,
        test_point_wave_natural_continuity_and_role_attribution_are_grounded,
    ]
    passed = []
    for test in tests:
        test()
        passed.append({"name": test.__name__, "passed": True})
    print(json.dumps({"status": "passed", "tests": passed}, ensure_ascii=False))
