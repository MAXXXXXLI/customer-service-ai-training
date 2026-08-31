from __future__ import annotations

import json
import re

import server


def scenario(scenario_id: str) -> dict:
    value = next((item for item in server.SCENARIOS if item.get("id") == scenario_id), None)
    assert value is not None, scenario_id
    return value


def ordinary_training_result(
    suggested_reply: str,
    *,
    employee_message: str = "好的，我知道了，那我们先做一次看看吧。",
    issue: str = "员工还没有回应顾客当前顾虑。",
    why: str = "需要先承接问题，再补一个必要信息。",
) -> dict:
    item = scenario("SCN-CEX-M01-S01")
    history = [{"role": "assistant", "content": item["opening"]}]
    return server.normalize_training_result(
        {
            "customer_reply": "我还是想先把区别听清楚。",
            "feedback": {
                "level": "needs_work",
                "issue": issue,
                "why": why,
                "method_step": "承接顾虑并澄清重点",
                "knowledge_focus": "顾客当前顾虑与必要信息",
                "suggested_reply": suggested_reply,
                "next_goal": "下一轮先回应顾客当前问题。",
            },
        },
        item,
        history,
        employee_message,
    )


def test_role_attribution_is_precise() -> None:
    customer_quote = "你们秀域到底是做什么的"
    legitimate = ordinary_training_result(
        "我理解您想先把秀域能提供什么弄清楚。我们先不急着安排；我先围绕您的肩颈困扰说明已核验的服务边界，您听清后再决定。",
        employee_message="我理解您想先听清楚，我先只回答肩颈这件事。",
        issue=f"员工没有完整回应顾客“{customer_quote}”这个问题。",
        why="这句话有承接，但还需要用已核验信息回答顾客问的内容。",
    )
    assert "顾客说过的话不能算成员工表达" not in legitimate["feedback"]["why"], legitimate
    assert legitimate["feedback"]["suggested_reply"].startswith("我理解您想先把情况"), legitimate
    assert "不急着" not in legitimate["feedback"]["suggested_reply"], legitimate

    false_attribution = ordinary_training_result(
        "我理解您想先把具体服务听清楚。我们先不急着安排；我先说明与肩颈困扰相关的已核验边界，您确认后再决定。",
        issue=f"员工原话是“{customer_quote}”。",
    )
    assert "顾客说过的话不能算成员工表达" in false_attribution["feedback"]["issue"], false_attribution


def test_bad_or_unverifiable_recommendations_are_repaired() -> None:
    employee = "好的，我知道了，那我们先做一次看看吧。"
    bad_replies = [
        employee,
        "我先了解X问题，再给您推荐Y项目，后续安排Z次体验。",
        "您最在意价格吗？还是最在意效果？我们马上安排。",
        "设备能精准控制作用深度并促进局部循环，所以很适合您。",
        "您可以服用布洛芬缓解，今天先休息，明天再继续体验。",
        "建议话术：员工应该调用对应QA，再根据评分给出下一轮回复。",
        "疼痛比原来加重需要先重视，今天先暂停后续项目；请完成记录和升级。",
    ]
    forbidden = re.compile(r"X问题|Y项目|Z次|精准控制|促进局部循环|服用布洛芬|建议话术|调用对应QA|疼痛比原来加重需要先重视")
    for bad in bad_replies:
        result = ordinary_training_result(bad, employee_message=employee)
        reply = result["feedback"]["suggested_reply"]
        assert reply != employee, {"input": bad, "output": reply}
        assert not forbidden.search(reply), {"input": bad, "output": reply}
        assert 20 <= len(reply) <= 180, {"input": bad, "output": reply}
        assert reply.count("？") + reply.count("?") <= 1, {"input": bad, "output": reply}


def test_faq_source_is_never_used_as_customer_speech() -> None:
    raw_source = "这个问题涉及点阵波服务后的观察和升级，应按当前课程与流程处理。"
    match = {"row": {"question": "点阵波后更痛怎么办？"}, "query": "点阵波后更痛怎么办？"}
    fallback = server.faq_customer_voice_fallback(match)
    assert server.faq_answer_needs_customer_voice_repair(raw_source)
    assert not server.faq_answer_needs_customer_voice_repair(fallback)
    assert "这个问题涉及" not in fallback and "当前课程" not in fallback
    assert "我先" in fallback and "您" in fallback

    question = server.COMMON_QA[0]["question"]
    raw_source = server.COMMON_QA[0]["approved_answer"]
    original_call_model = server.call_model

    def fake_call_model(system: str, messages: list[dict[str, str]], *args: object, **kwargs: object) -> tuple[str, dict]:
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            return json.dumps({"match_id": server.COMMON_QA[0]["id"], "confidence": 0.99, "answer": raw_source}), {}
        return json.dumps({"answer": raw_source, "uncertainties": [], "recommended_action": ""}), {}

    server.call_model = fake_call_model
    try:
        response = server.handle_chat({"mode": "qa", "message": question, "api_key": "test-key"})
    finally:
        server.call_model = original_call_model
    answer = response["result"]["answer"]
    assert response["meta"]["common_qa"] is True, response
    assert answer != raw_source and "这个问题涉及" not in answer, response
    assert "我先" in answer and "您" in answer, response


def test_qa_final_answer_repairs_policy_voice_across_paths() -> None:
    route = server.route_customer_question("敏感肌能做水光吗？")
    repaired = server.apply_methodology_result(
        {
            "answer": "当前应按SOP完成确认，门店不能直接判断，并按异常流程处理。",
            "uncertainties": [],
            "recommended_action": "先确认。",
        },
        "qa",
        route,
        "敏感肌能做水光吗？",
    )
    assert "我" in repaired["answer"], repaired
    assert not re.search(r"SOP|门店不能|按异常流程|当前应", repaired["answer"]), repaired

    mock = server.mock_qa_response(
        "肩颈不舒服想了解一下",
        server.route_customer_question("肩颈不舒服想了解一下"),
        [{"document_id": "demo", "text": "课程里的流程摘要", "metadata": {"title": "演示课程"}}],
    )
    assert "知识库相关课程提到" not in mock["answer"], mock
    assert "我" in mock["answer"], mock

    original_call_model = server.call_model
    server.call_model = lambda *args, **kwargs: (
        json.dumps({"answer": "当前应按SOP执行，门店不能直接判断，并按异常流程处理。", "uncertainties": [], "recommended_action": "按流程"}),
        {},
    )
    try:
        model_answer = server.handle_chat({"mode": "qa", "message": "肩颈感觉紧，想了解一下", "api_key": "test-key"})["result"]["answer"]
    finally:
        server.call_model = original_call_model
    assert "我" in model_answer, model_answer
    assert not re.search(r"SOP|门店不能|按异常流程|当前应", model_answer), model_answer

    for question in ("超V副作用有哪些？", "敏感肌能做水光吗？", "司美格鲁肽怎么停？"):
        answer = server.handle_chat({"mode": "qa", "message": question})["result"]["answer"]
        assert "我" in answer, {"question": question, "answer": answer}
        assert not re.search(r"SOP|门店不能|按异常流程|当前应|本次应", answer), {"question": question, "answer": answer}


def test_model_cannot_self_certify_a_bad_employee_reply() -> None:
    item = scenario("SCN-CEX-M01-S01")
    history = [{"role": "assistant", "content": item["opening"]}]
    employee = "好的，我知道了，那我们先做一次看看吧。"
    result = server.normalize_training_result(
        {
            "customer_reply": "我还没听懂。",
            "feedback": {
                "level": "good",
                "issue": "回答很好。",
                "why": "模型认为可以继续。",
                "method_step": "安排项目",
                "knowledge_focus": "项目安排",
                "suggested_reply": employee,
                "next_goal": "成交。",
            },
        },
        item,
        history,
        employee,
    )
    assert result["feedback"]["suggested_reply"] != employee, result


def test_irrelevant_emergency_script_is_not_good() -> None:
    item = scenario("SCN-CEX-M02-S01")
    history = [{"role": "assistant", "content": item["opening"]}]
    employee = "今天先停止所有项目，我们不在店内判断原因。我会记录并上报负责人，并建议您尽快由医疗机构评估。"
    result = server.normalize_training_result(
        {
            "customer_reply": "我问的是价格。",
            "feedback": {
                "level": "good",
                "issue": "安全闭环完整。",
                "why": "已经暂停并分流。",
                "suggested_reply": employee,
            },
        },
        item,
        history,
        employee,
    )
    assert result["feedback"]["level"] == "needs_work", result
    assert "价格" in result["feedback"]["suggested_reply"], result


def test_assessment_requires_dimension_specific_employee_evidence() -> None:
    history = [
        {"role": "assistant", "content": "你们这个太贵了，我为什么要在你们这里做？"},
        {"role": "user", "content": "好的。"},
    ]
    dimensions = [
        {
            "id": item["id"],
            "score": item["weight"],
            "evidence": "员工原话：“好的。”",
            "comment": "表现优秀。",
        }
        for item in server.RUBRIC["dimensions"]
    ]
    report = server.normalize_assessment_result(
        {
            "dimension_scores": dimensions,
            "strengths": ["全部完成。"],
            "improvements": ["无需改进。"],
            "summary": "满分。",
        },
        history,
    )
    assert report["total_score"] == 0, report
    assert all(item["score"] == 0 and item["evidence"] == "对话中未体现" for item in report["dimension_scores"]), report


def test_service_side_effects_do_not_route_to_drug_ai() -> None:
    expected = {
        "冰雕有什么副作用？": ("INTENT-SUITABILITY", "MOD-07"),
        "超V有什么副作用？": ("INTENT-SUITABILITY", "MOD-04"),
        "热玛吉有什么副作用？": ("INTENT-SUITABILITY", "MOD-09"),
        "点阵波有什么副作用？": ("INTENT-SUITABILITY", "MOD-03"),
        "纳米喷射有什么副作用？": ("INTENT-SUITABILITY", "MOD-08"),
        "磁波内雕有什么副作用？": ("INTENT-SUITABILITY", "MOD-08"),
        "智能提拉有什么副作用？": ("INTENT-SUITABILITY", "MOD-08"),
        "头皮养护有什么副作用？": ("INTENT-SUITABILITY", "MOD-08"),
        "超声炮有什么副作用？": ("INTENT-SUITABILITY", "MOD-09"),
        "司美格鲁肽有什么副作用？": ("INTENT-DRUG", "MOD-06"),
    }
    for question, wanted in expected.items():
        route = server.route_customer_question(question)
        assert (route["intent_id"], route["primary_module_id"]) == wanted, {"question": question, "route": route}


def test_public_action_is_route_owned_and_blocks_model_invention() -> None:
    route = server.route_customer_question("冰雕适不适合做腰腹？")
    invented_action = "请告诉我肚子脂肪的触感是软还是硬，以便我为您做进一步评估。"
    normalized = server.apply_methodology_result(
        {"answer": "先核对状态再说明。", "uncertainties": [], "recommended_action": invented_action},
        "qa",
        route,
    )
    assert normalized["recommended_action"] == server.public_recommended_action(route), normalized
    assert normalized["recommended_action"] != invented_action, normalized

    internal = server.apply_methodology_result(
        {"answer": "先核对状态再说明。", "uncertainties": [], "recommended_action": "调用对应具体QA并读取知识库。"},
        "qa",
        route,
    )
    assert not server.QA_INTERNAL_ACTION_PATTERN.search(internal["recommended_action"]), internal
    assert "局部皮肤" in internal["recommended_action"], internal


def test_drug_safety_language_matches_age_context() -> None:
    adult = server.handle_chat({"mode": "qa", "message": "我是35岁成年人，使用司美格鲁肽前要注意什么？"})["result"]["answer"]
    negative_adult = server.handle_chat({"mode": "qa", "message": "我不是儿童，我35岁，使用司美格鲁肽前要注意什么？"})["result"]["answer"]
    self_adult = server.handle_chat({"mode": "qa", "message": "不是给孩子，是我本人，35岁，司美格鲁肽怎么用？"})["result"]["answer"]
    child = server.handle_chat({"mode": "qa", "message": "我家孩子能不能用减肥药？"})["result"]["answer"]
    assert "儿童或未成年人" not in adult, adult
    assert "儿童或未成年人" not in negative_adult, negative_adult
    assert "儿童或未成年人" not in self_adult, self_adult
    assert "儿童或未成年人" in child, child
    assert all(word in adult for word in ("医生", "剂量", "门店")), adult


def test_unsafe_actions_and_training_prescriptions_are_blocked() -> None:
    route = server.route_customer_question("冰雕适不适合做腰腹？")
    for action in (
        "您回去把司美格鲁肽停了，改成每天两片。",
        "请检索并引用对应的标准问答条目。",
    ):
        result = server.apply_methodology_result(
            {"answer": "需要先核对。", "uncertainties": [], "recommended_action": action},
            "qa",
            route,
        )
        assert result["recommended_action"] != action, result
        assert not server.QA_UNSAFE_ACTION_PATTERN.search(result["recommended_action"]), result

    for suggested in (
        "您回去吃一片布洛芬缓解，先观察一下身体情况，有问题再联系门店。",
        "您回家后可以服用双氯芬酸缓释片缓解不适，今天先休息观察。",
    ):
        result = ordinary_training_result(suggested)
        assert suggested != result["feedback"]["suggested_reply"], result
        assert "布洛芬" not in result["feedback"]["suggested_reply"]
        assert "双氯芬酸" not in result["feedback"]["suggested_reply"]


def test_endure_drug_and_fixed_result_failures_are_critical() -> None:
    item = scenario("SCN-CEX-M03-S02")
    history = [{"role": "assistant", "content": item["opening"]}]
    endure = "是的，辛苦您忍几分钟。如果您实在很痛，我可以先帮您把力度调低一些。"
    result = server.normalize_training_result(
        {"customer_reply": "我还是很痛。", "feedback": {"level": "good", "suggested_reply": endure}},
        item,
        history,
        endure,
    )
    assert result["feedback"]["level"] == "critical", result

    unsafe_history = [
        {"role": "assistant", "content": "我正在用司美格鲁肽，今天有点不舒服。"},
        {"role": "user", "content": "把司美格鲁肽停了，改成每天两片。"},
        {"role": "user", "content": "这个项目一定见效。"},
    ]
    details = server.detect_assessment_failure_details(unsafe_history)
    assert "CF-02" in details, details
    assert server.unsafe_claim_hits("这个项目肯定出结果。"), "fixed result promise escaped"


def test_irrelevant_employee_text_cannot_be_good() -> None:
    item = scenario("SCN-CEX-M02-S01")
    history = [{"role": "assistant", "content": item["opening"]}]
    for message in ("好的。", "今天天气不错。", "你的肩颈疼了多久？"):
        result = server.normalize_training_result(
            {"customer_reply": "我问的是价格。", "feedback": {"level": "good", "suggested_reply": "我理解您的担心，我们先安排一次体验再说。"}},
            item,
            history,
            message,
        )
        assert result["feedback"]["level"] == "needs_work", {"message": message, "result": result}
        assert "价格" in result["feedback"]["suggested_reply"], result


def test_route_aware_weknora_enrichment_and_grounded_risk_copy() -> None:
    route = server.route_customer_question("冰雕有什么副作用？")

    class FakeSearch:
        configured = True

        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str, limit: int = 8) -> list[dict]:
            self.queries.append(query)
            if "轰脂、冰雕与抽脂" not in query:
                return []
            return [{
                "document_id": "COURSE-NKB-030",
                "text": "服务后可能出现局部红感、酸胀、触痛或硬结感。",
                "metadata": {"doc_type": "course_section", "course_id": "COURSE-NKB-030", "module_id": "MOD-07"},
                "weknora": {"chunk_id": "chunk-030"},
            }]

    original = server.WEKNORA_SEARCH
    fake = FakeSearch()
    server.WEKNORA_SEARCH = fake
    try:
        docs = server.retrieve("冰雕有什么副作用？", route=route)
    finally:
        server.WEKNORA_SEARCH = original
    assert len(fake.queries) == 2 and "轰脂、冰雕与抽脂" in fake.queries[1], fake.queries
    assert docs[0]["metadata"]["course_id"] == "COURSE-NKB-030", docs
    grounded = server.deterministic_service_risk_result("冰雕有什么副作用？", route)
    assert grounded and all(word in grounded["answer"] for word in ("红感", "酸胀", "触痛", "硬结", "暂停")), grounded


def test_customer_simulator_rejects_premature_push() -> None:
    for scenario_id in ("SCN-CEX-M03-S01", "SCN-CEX-M06-S01", "SCN-CEX-M10-S01"):
        item = scenario(scenario_id)
        reply = server.test_fallback_reply(item, [{"role": "assistant", "content": item["opening"]}], "好的，那我们先做一次看看吧。")
        assert "还没" in reply and ("回答" in reply or "说清" in reply), {"scenario": scenario_id, "reply": reply}


def test_point_wave_direct_coverage_never_degrades_to_generic_clarification() -> None:
    question = "点阵波的原理是什么？"
    route = server.route_customer_question(question)
    faq = next(item for item in server.COMMON_QA if item.get("id") == "FAQ-XLS-0007")
    generic_pattern = re.compile(r"最想了解的是(?:体验感受|感受)、?(?:适用性|服务后的变化)|围绕您刚才提到的项目说明", re.I)

    direct = server.grounded_customer_qa_fallback(question)
    assert direct, direct
    assert all(term in direct for term in ("点阵波", "机械刺激")), direct
    assert re.search(r"震动|敲击|酸胀", direct), direct
    assert re.search(r"医学诊断|医疗人员", direct), direct
    assert "固定效果承诺" in direct, direct
    assert not generic_pattern.search(direct), direct

    faq_fallback = server.faq_customer_voice_fallback({"row": faq, "query": question})
    assert faq_fallback == direct, {"direct": direct, "faq_fallback": faq_fallback}
    assert server.qa_employee_voice_fallback(question, route) == direct

    docs = server.retrieve_local(question, route=route)
    mock = server.mock_qa_response(question, route, docs)
    assert mock["answer"] == direct, mock
    assert not mock["uncertainties"], mock

    # Model output can be fluent yet still evade the question. The final QA
    # guard must replace it only because this direct topic has reviewed
    # evidence; unrelated missing-material questions retain ordinary
    # clarification behaviour.
    original_call_model = server.call_model

    def fake_call_model(system: str, *args: object, **kwargs: object) -> tuple[str, dict]:
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            return json.dumps({"match_id": "NONE", "confidence": 0, "answer": ""}), {}
        return json.dumps({
            "answer": "我会先围绕您刚才提到的项目说明已核验的信息。麻烦您告诉我最想了解的是体验感受、适用性还是服务后的变化。",
            "uncertainties": [],
            "recommended_action": "继续说明。",
        }), {}

    server.call_model = fake_call_model
    try:
        online = server.handle_chat({"mode": "qa", "message": question, "api_key": "test-key"})
    finally:
        server.call_model = original_call_model
    answer = online["result"]["answer"]
    assert all(term in answer for term in ("点阵波", "机械刺激")), online
    assert not generic_pattern.search(answer), online

    aftercare = server.handle_chat({"mode": "qa", "message": "我做完点阵波后更痛了"})["result"]["answer"]
    assert "暂停" in aftercare and "负责人" in aftercare, aftercare
    assert "机械刺激体验" not in aftercare, aftercare


def test_prompt_contains_recommendation_quality_contract() -> None:
    prompt = server.TRAIN_FEEDBACK_SYSTEM
    for marker in ("直接对顾客说", "最多一个问号", "不得使用 X/Y/Z", "精准控制深度", "自检"):
        assert marker in prompt, marker


def main() -> None:
    tests = [
        test_role_attribution_is_precise,
        test_bad_or_unverifiable_recommendations_are_repaired,
        test_faq_source_is_never_used_as_customer_speech,
        test_qa_final_answer_repairs_policy_voice_across_paths,
        test_model_cannot_self_certify_a_bad_employee_reply,
        test_irrelevant_emergency_script_is_not_good,
        test_assessment_requires_dimension_specific_employee_evidence,
        test_service_side_effects_do_not_route_to_drug_ai,
        test_public_action_is_route_owned_and_blocks_model_invention,
        test_drug_safety_language_matches_age_context,
        test_unsafe_actions_and_training_prescriptions_are_blocked,
        test_endure_drug_and_fixed_result_failures_are_critical,
        test_irrelevant_employee_text_cannot_be_good,
        test_route_aware_weknora_enrichment_and_grounded_risk_copy,
        test_customer_simulator_rejects_premature_push,
        test_point_wave_direct_coverage_never_degrades_to_generic_clarification,
        test_prompt_contains_recommendation_quality_contract,
    ]
    rows = []
    for test in tests:
        test()
        rows.append({"name": test.__name__, "passed": True})
    print(json.dumps({"status": "passed", "tests": rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
