from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def course_ids(result: dict) -> list[str]:
    return [item.get("course_id", "") for item in result.get("retrieved", []) if item.get("course_id")]


query_side_effect = "点阵波的副作用有哪些"
side_effect_candidates = server.common_qa_candidates(query_side_effect)
check(side_effect_candidates, "副作用问题应能生成多个候选问答")
check(server.match_common_qa(query_side_effect) is None, "副作用不能直接命中项目定义问答")
selected_without_api, selection_meta = server.select_common_qa_with_model(query_side_effect, side_effect_candidates, "test", "")
check(selected_without_api is None, "没有 API 时低置信度候选必须回退知识库")
check(selection_meta.get("selection") == "fallback_knowledge", "低置信度候选应标记为知识库回退")

side_effect_result = server.handle_chat({"mode": "qa", "message": query_side_effect})
check(not side_effect_result["result"].get("faq_match"), "副作用问题不能展示错误的常见问答匹配")
check(course_ids(side_effect_result) == ["COURSE-NKB-012"], "副作用问题只能引用服务后反应课程")
check("点阵波" in side_effect_result["result"].get("answer", ""), "回退回答必须承接当前问题")

exact_result = server.handle_chat({"mode": "qa", "message": "点阵波打完更痛了怎么办"})
check(exact_result["result"].get("faq_match", {}).get("id") == "FAQ-XLS-0002", "相同问题应命中对应标准问答")
check(course_ids(exact_result) == ["COURSE-NKB-012"], "服务后疼痛问答只能引用服务后反应课程")

typo_result = server.handle_chat({"mode": "qa", "message": "点振波的副作用有哪些"})
check(typo_result["result"]["route"].get("primary_module") == "点阵波与疼痛服务", "点振波错别字仍应进入点阵波模块")
check(course_ids(typo_result) == ["COURSE-NKB-012"], "点振波错别字应检索服务后反应课程")

original_call_model = server.call_model
try:
    def fake_model(system, messages, model, api_key, temperature=0.4, max_tokens=1800):
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            payload = json.loads(messages[0]["content"])
            selected = payload["candidates"][0]
            return json.dumps({
                "match_id": selected["id"],
                "confidence": 0.95,
                "answer": selected["approved_answer"],
                "reason": "候选问题与当前问题意图一致",
            }, ensure_ascii=False), {"model": model, "usage": {"total_tokens": 10}}
        return json.dumps({
            "answer": "知识库回退回答：先围绕当前问题说明已核验内容。",
            "uncertainties": [],
            "recommended_action": "继续核对当前课程。",
        }, ensure_ascii=False), {"model": model, "usage": {"total_tokens": 20}}

    server.call_model = fake_model
    api_selected = server.handle_chat({"mode": "qa", "message": query_side_effect, "api_key": "test-key"})
    check(api_selected["result"].get("faq_match"), "API 二次判断选中候选后应返回标准问答")
    check(api_selected["meta"].get("selection") == "model_judged", "API 选中候选应标记为模型判断")
    check(len(api_selected.get("retrieved", [])) == 1, "标准问答结果不能混入通用课程")

    def fake_none_model(system, messages, model, api_key, temperature=0.4, max_tokens=1800):
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            return json.dumps({"match_id": "NONE", "confidence": 0.95, "answer": "", "reason": "候选不能直接回答"}), {"model": model, "usage": {}}
        return json.dumps({"answer": "知识库回退回答：只回答当前问题。", "uncertainties": [], "recommended_action": "继续核对当前课程。"}), {"model": model, "usage": {}}

    server.call_model = fake_none_model
    api_fallback = server.handle_chat({"mode": "qa", "message": query_side_effect, "api_key": "test-key"})
    check(not api_fallback["result"].get("faq_match"), "模型判定 NONE 后必须回退知识库回答")
    check(api_fallback["meta"].get("selection") == "fallback_knowledge", "模型判定 NONE 应标记知识库回退")
finally:
    server.call_model = original_call_model

print(json.dumps({
    "status": "passed",
    "candidate_count": len(side_effect_candidates),
    "fallback_courses": course_ids(side_effect_result),
    "exact_match": exact_result["result"]["faq_match"]["id"],
    "typo_course": course_ids(typo_result),
}, ensure_ascii=False, indent=2))
