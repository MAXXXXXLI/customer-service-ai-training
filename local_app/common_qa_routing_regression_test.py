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
check(not exact_result["result"].get("faq_match"), "隔离中的争议 FAQ 不得作为已发布问答展示")
check(course_ids(exact_result) == [], "确定性安全答复不得依赖检索服务")
check(exact_result["result"].get("answer") == server.POINT_WAVE_BEST_REPLY, "点阵波服务后更痛必须返回固定安全回答")
check(exact_result["meta"].get("selection") == "deterministic_safety", "安全回答必须先于 FAQ、检索和模型执行")

for similar_query in (
    "点振波打完第二天更痛",
    "点阵波理疗后更酸痛是不是正常",
    "我昨天做完点阵波今天比原来更疼",
    "做完点阵波是不是把我打坏了",
):
    similar_result = server.handle_chat({"mode": "qa", "message": similar_query})
    check(not similar_result["result"].get("faq_match"), f"相似问法不得命中隔离 FAQ：{similar_query}")
    check(similar_result["result"].get("answer") == server.POINT_WAVE_BEST_REPLY, f"相似问法未返回固定安全回答：{similar_query}")
    check(course_ids(similar_result) == [], f"相似安全问法不应依赖检索：{similar_query}")

for resolved_query in (
    "点阵波做完已经不痛了，正常吗",
    "点阵波打完没有更痛，正常吗",
    "点阵波做完疼痛没有加剧，正常吗",
    "点阵波服务后并未恶化，正常吗",
):
    resolved_result = server.handle_chat({"mode": "qa", "message": resolved_query})
    check(resolved_result["meta"].get("selection") != "deterministic_safety", f"已缓解或明确未加重不得误判：{resolved_query}")

for renewed_query in (
    "点阵波做完先缓解了但今天又更痛",
    "点阵波打完未减轻反而更痛",
    "点阵波服务后疼痛比之前严重了",
    "做完点阵波疼得更厉害了",
    "昨天点阵波做完疼痛加剧",
    "点阵波服务后越来越痛",
    "做完点阵波后疼痛恶化",
    "做了点阵波以后疼痛加重",
    "点阵波做过之后更疼",
    "点阵波治疗后越来越痛",
    "今天刚做点阵波，疼得更厉害了",
    "点阵波做完疼痛现在没有缓解，正常吗",
    "点阵波做完疼痛目前未减轻，正常吗",
    "点阵波做完疼痛更严重了",
    "点阵波做完又痛起来了",
    "体验后当时没有更痛，后来反而更疼了，点阵波该怎么办",
    "点阵波已经缓解，但今天又更痛",
):
    renewed_result = server.handle_chat({"mode": "qa", "message": renewed_query})
    check(renewed_result["meta"].get("selection") == "deterministic_safety", f"再次加重必须优先安全处理：{renewed_query}")

for post_service_risk_query in (
    "点阵波后更痛了",
    "做点阵波之后疼痛加剧",
    "点阵波结束后疼得更厉害",
    "小通机器人打完第二天更疼",
    "点阵波做完痛得受不了",
    "点阵波刚做完痛到睡不着",
    "点阵波理疗后一直疼",
    "点阵波做完疼痛持续两天了",
    "点阵波做完已经缓解今天又更痛了",
    "点阵波做完现在不痛今天又疼起来了",
    "昨天做的点阵波今天更痛",
):
    risk_result = server.handle_chat({"mode": "qa", "message": post_service_risk_query})
    check(risk_result["meta"].get("selection") == "deterministic_safety", f"服务后严重、持续或加重必须本地安全处理：{post_service_risk_query}")
    check("暂停" in risk_result["result"].get("answer", ""), f"服务后风险答复必须给出暂停动作：{post_service_risk_query}")
    check(course_ids(risk_result) == [], f"确定性服务后安全答复不得依赖检索：{post_service_risk_query}")

for non_worsening_query in (
    "点阵波做完没有疼痛，正常吗",
    "点阵波做完没有酸痛，正常吗",
    "点阵波做完痛感没变，正常吗",
    "点阵波做完疼痛比之前轻了，正常吗",
    "点阵波做完疼痛减轻了但没完全好，正常吗",
    "点阵波做完一开始更痛，后来已经缓解了，正常吗",
):
    non_worsening_result = server.handle_chat({"mode": "qa", "message": non_worsening_query})
    check(non_worsening_result["meta"].get("selection") != "deterministic_safety", f"无痛、改善或不变不得误判为加重：{non_worsening_query}")
    check(not non_worsening_result["result"]["route"].get("stop_sales"), f"无痛、改善或不变不得进入停止销售路由：{non_worsening_query}")
    check("比原来加重" not in non_worsening_result["result"].get("answer", ""), f"答复不得虚构疼痛加重：{non_worsening_query}")

follow_up_result = server.handle_chat({
    "mode": "qa",
    "message": "那现在怎么办？",
    "history": [
        {"role": "user", "content": "我做了点阵波以后疼痛加重了。"},
        {"role": "assistant", "content": "我先了解一下您的情况。"},
    ],
})
check(follow_up_result["meta"].get("selection") == "deterministic_safety", "多轮追问必须继承上一轮的服务后加重事实")
check("暂停" in follow_up_result["result"].get("answer", ""), "多轮安全追问必须给出暂停动作")

resolved_follow_up = server.handle_chat({
    "mode": "qa",
    "message": "那现在已经不痛了，怎么办？",
    "history": [
        {"role": "user", "content": "我点阵波打完更痛了。"},
        {"role": "assistant", "content": "今天先暂停后续项目。"},
    ],
})
check(resolved_follow_up["meta"].get("selection") != "deterministic_safety", "当前轮明确恢复必须覆盖旧的加重状态")
check(not resolved_follow_up["result"]["route"].get("stop_sales"), "当前轮明确恢复不得继续沿用旧的停止销售路由")

for hypothetical_query in (
    "我还没做点阵波，只是昨天腰更疼，能做吗",
    "朋友说点阵波做完更痛，我想了解它是什么",
    "点阵波会不会做完更痛？",
    "如果点阵波做完更痛怎么办？",
    "我想问点阵波以后会更疼吗？",
    "我昨天腰比原来更痛，点阵波是什么？",
    "点阵波昨天做完感觉很好，多久做一次",
    "昨天做完点阵波没什么不舒服，效果不错",
    "昨天做完点阵波想问价格",
    "做完点阵波会更痛吗",
    "做完点阵波是不是会更痛",
    "做点阵波后会痛到睡不着吗",
    "我怕做完点阵波痛得受不了",
):
    hypothetical_result = server.handle_chat({"mode": "qa", "message": hypothetical_query})
    check(hypothetical_result["meta"].get("selection") != "deterministic_safety", f"非本人异常或已明确无不适不得误触安全短路：{hypothetical_query}")
    check(not hypothetical_result["result"]["route"].get("stop_sales"), f"非异常问法不得进入停止销售路由：{hypothetical_query}")

price_safety = server.handle_chat({"mode": "qa", "message": "点阵波体验后疼痛加重了，价格怎么算"})
check(price_safety["meta"].get("selection") == "deterministic_safety", "价格组合意图仍须安全优先")
check("暂停" in price_safety["result"].get("answer", "") and "城市、门店" not in price_safety["result"].get("answer", ""), "价格不得覆盖安全答复")

red_flag_result = server.handle_chat({"mode": "qa", "message": "点阵波做完更疼而且手麻"})
check("急救" in red_flag_result["result"].get("answer", "") and "有没有麻木" not in red_flag_result["result"].get("answer", ""), "已知红旗必须直接承接并紧急分流")

negated_red_flag = server.handle_chat({"mode": "qa", "message": "我有颈椎病但没有麻木无力，能做点阵波吗"})
check("已有相关诊断" in negated_red_flag["result"].get("answer", ""), "已有诊断应走医疗确认边界")
check("您已经提到需要优先处理的异常" not in negated_red_flag["result"].get("answer", ""), "否认麻木无力时不得虚构已出现红旗")

for hypothetical_red_flag_query in (
    "点阵波会不会导致胸痛",
    "如果做完点阵波手麻怎么办",
    "听说点阵波做完会胸闷是真的吗",
):
    hypothetical_red_flag = server.handle_chat({"mode": "qa", "message": hypothetical_red_flag_query})
    check(not hypothetical_red_flag["result"]["route"].get("stop_sales"), f"假设或转述症状不得当作已经发生：{hypothetical_red_flag_query}")
    check("已经出现需要优先处理的异常" not in hypothetical_red_flag["result"].get("answer", ""), f"假设症状不得触发已发生式紧急话术：{hypothetical_red_flag_query}")

for colloquial_red_flag_query in (
    "点阵波做完胸口疼",
    "点阵波做完喘不过气",
    "点阵波做完晕倒了",
    "点阵波做完手没劲",
    "点阵波做完大小便失禁",
):
    colloquial_red_flag = server.handle_chat({"mode": "qa", "message": colloquial_red_flag_query})
    check(colloquial_red_flag["result"]["route"].get("stop_sales"), f"口语红旗必须停止项目并分流：{colloquial_red_flag_query}")
    check("急救" in colloquial_red_flag["result"].get("answer", ""), f"口语红旗必须返回紧急医疗分流：{colloquial_red_flag_query}")

for negated_colloquial_query in ("没有胸口疼，只是问价格", "没有喘不过气，能做吗"):
    negated_colloquial = server.handle_chat({"mode": "qa", "message": negated_colloquial_query})
    check(not negated_colloquial["result"]["route"].get("stop_sales"), f"否认的口语红旗不得误分流：{negated_colloquial_query}")

short_status_history = [
    {"role": "user", "content": "点阵波做完以后有点疼"},
    {"role": "assistant", "content": "现在缓解还是加重？"},
]
for short_status in ("更严重了", "更痛了", "还是很痛", "一直没缓解", "现在痛得受不了"):
    short_status_result = server.handle_chat({"mode": "qa", "message": short_status, "history": short_status_history})
    check(short_status_result["meta"].get("selection") == "deterministic_safety", f"短状态追答必须继承点阵波服务后上下文：{short_status}")

red_flag_history = [
    {"role": "user", "content": "点阵波做完疼痛加重，而且手麻了"},
    {"role": "assistant", "content": "今天先暂停后续项目。"},
]
pain_only_resolved = server.handle_chat({"mode": "qa", "message": "那疼痛已经缓解了", "history": red_flag_history})
check(pain_only_resolved["result"]["route"].get("stop_sales"), "只说疼痛缓解不得丢失历史未确认的手麻红旗")
all_resolved = server.handle_chat({"mode": "qa", "message": "那疼痛和手麻都缓解了", "history": red_flag_history})
check(not all_resolved["result"]["route"].get("stop_sales"), "明确疼痛和手麻均缓解后不得继续声称异常正在发生")

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
    selected, selected_meta = server.select_common_qa_with_model(
        query_side_effect, side_effect_candidates, "test", "test-key"
    )
    check(selected is not None, "API 二次判断应能在候选层返回被模型选中的标准问答")
    check(selected_meta.get("selection") == "model_judged", "API 选中候选应标记为模型判断")

    # 服务风险问法已经有更高优先级、由权威课程约束的确定性答案；
    # 即使 FAQ 判断模型愿意选中候选，也不能绕过这条安全路由。
    api_selected = server.handle_chat({"mode": "qa", "message": query_side_effect, "api_key": "test-key"})
    check(not api_selected["result"].get("faq_match"), "确定性服务风险答案不得伪装成已审批 FAQ")
    check(api_selected["meta"].get("selection") == "deterministic_service_risk", "服务风险答案必须先于 FAQ 模型判断")

    def fake_none_model(system, messages, model, api_key, temperature=0.4, max_tokens=1800):
        if system == server.COMMON_QA_JUDGE_SYSTEM:
            return json.dumps({"match_id": "NONE", "confidence": 0.95, "answer": "", "reason": "候选不能直接回答"}), {"model": model, "usage": {}}
        return json.dumps({"answer": "知识库回退回答：只回答当前问题。", "uncertainties": [], "recommended_action": "继续核对当前课程。"}), {"model": model, "usage": {}}

    server.call_model = fake_none_model
    fallback_selected, fallback_meta = server.select_common_qa_with_model(
        query_side_effect, side_effect_candidates, "test", "test-key"
    )
    check(fallback_selected is None, "模型判定 NONE 后候选层必须拒绝 FAQ")
    check(fallback_meta.get("selection") == "fallback_knowledge", "模型判定 NONE 应标记知识库回退")
finally:
    server.call_model = original_call_model

print(json.dumps({
    "status": "passed",
    "candidate_count": len(side_effect_candidates),
    "fallback_courses": course_ids(side_effect_result),
    "exact_match": exact_result["result"].get("faq_match"),
    "best_answer_selection": exact_result["meta"].get("selection"),
    "typo_course": course_ids(typo_result),
}, ensure_ascii=False, indent=2))
