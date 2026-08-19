from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = ROOT / "knowledge_base"
STATIC_ROOT = Path(__file__).resolve().parent / "static"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8787"))
SILICONFLOW_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1/chat/completions")
DEFAULT_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen3.5-35B-A3B")
ENV_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
MOCK_MODE = os.getenv("SILICONFLOW_MOCK", "0").lower() in {"1", "true", "yes"}
AVAILABLE_MODELS = [
    {"id": "Qwen/Qwen3.5-35B-A3B", "label": "Qwen 3.5 35B · 推荐"},
    {"id": "deepseek-ai/DeepSeek-V3.2", "label": "DeepSeek V3.2 · 高质量"},
    {"id": "Qwen/Qwen3.5-27B", "label": "Qwen 3.5 27B · 稳定"},
    {"id": "Pro/zai-org/GLM-5.1", "label": "GLM 5.1 Pro"},
    {"id": "Pro/moonshotai/Kimi-K2.6", "label": "Kimi K2.6 Pro"},
    {"id": "MiniMaxAI/MiniMax-M2.5", "label": "MiniMax M2.5"},
]


def read_json(name: str) -> Any:
    return json.loads((KB_ROOT / name).read_text(encoding="utf-8"))


def read_jsonl(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (KB_ROOT / name).read_text(encoding="utf-8").splitlines() if line.strip()]


RAG_DOCUMENTS = read_jsonl("rag_documents.jsonl")
CARDS = read_jsonl("knowledge_cards.jsonl")
OBJECTIONS = read_jsonl("objection_library.jsonl")
SCENARIOS = read_jsonl("scenario_library.jsonl")
RUBRIC = read_json("scoring_rubric.json")
SOURCE_REGISTRY = read_json("source_registry.json")["sources"]
LEARNING_CATALOG = read_json("learning_catalog.json")
LEARNING_MODULES = read_json("learning_modules.json")["modules"]
METHODOLOGY = read_json("customer_service_methodology.json")
PUBLIC_TITLE_BY_ID = {
    course["id"].removeprefix("COURSE-"): course["title"]
    for course in LEARNING_CATALOG["courses"]
}
COURSE_BY_KNOWLEDGE_ID = {
    course["id"].removeprefix("COURSE-"): course
    for course in LEARNING_CATALOG["courses"]
}
COURSE_BY_ID = {course["id"]: course for course in LEARNING_CATALOG["courses"]}
MODULE_BY_ID = {module["id"]: module for module in LEARNING_MODULES}
SOURCE_TO_COURSES: dict[str, list[dict[str, Any]]] = {}
for item in [*CARDS, *OBJECTIONS]:
    course = COURSE_BY_KNOWLEDGE_ID.get(item.get("id", ""))
    if not course:
        continue
    for source_id in item.get("source_ids", []):
        SOURCE_TO_COURSES.setdefault(source_id, []).append(course)

DOMAIN_TO_MODULE = {
    "onboarding": "MOD-01", "company": "MOD-01", "reception": "MOD-01", "sales_skills": "MOD-01",
    "point_wave": "MOD-02", "point_wave_ops": "MOD-02", "professional_qa": "MOD-02", "training_video": "MOD-02",
    "super_v": "MOD-03", "point_wave_super_v": "MOD-03",
    "beauty": "MOD-04", "beauty_ops": "MOD-04",
    "slimming": "MOD-05", "slimming_reception": "MOD-05", "slimming_product": "MOD-05", "slimming_science": "MOD-05",
    "objections": "MOD-06", "comparison": "MOD-06",
    "safety": "MOD-07", "service_safety": "MOD-07", "operations": "MOD-07", "product_ops": "MOD-07",
}

DOMAIN_LABELS = {
    "onboarding": "新员工成长路径",
    "reception": "顾客接待与需求分析",
    "sales_skills": "顾客沟通与信任建立",
    "objections": "异议沟通与回应",
    "follow_up": "体验后回访与跟进",
    "point_wave": "点阵波项目知识",
    "super_v": "超V热动力项目知识",
    "beauty": "美容护理项目知识",
    "slimming": "科学体重管理",
    "slimming_reception": "体重管理接待流程",
    "slimming_product": "体重管理产品安全",
    "service_safety": "顾客服务与安全",
    "safety": "安全与合规底线",
    "operations": "门店运营规则",
    "product_ops": "项目与运营知识",
    "comparison": "项目比较与异议处理",
    "training_video": "基础项目培训要点",
}


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def unique_items(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def route_customer_question(query: str) -> dict[str, Any]:
    """Deterministically map a customer question to the approved knowledge modules."""
    text = clean_text(query)
    intent_routes = sorted(METHODOLOGY.get("intent_routes", []), key=lambda item: -item.get("priority", 0))
    intent = next((item for item in intent_routes if matches_any(text, item.get("patterns", []))), None)
    matched_intent = intent is not None
    topics = [item for item in METHODOLOGY.get("topic_routes", []) if matches_any(text, item.get("patterns", []))]
    default = METHODOLOGY.get("default_route", {})
    if not intent:
        if topics:
            intent = {
                "id": "INTENT-INFORMATION",
                "label": topics[0].get("label", "项目原理、流程与一般咨询"),
                "primary_module_id": "DYNAMIC",
                "support_module_ids": [],
                "course_ids": [],
                "focus": topics[0].get("recommended_next", "使用对应项目课程回答。"),
                "stop_sales": False,
            }
        else:
            intent = {
                "id": default.get("intent_id", "INTENT-INFORMATION"),
                "label": default.get("intent_label", "一般需求咨询"),
                "primary_module_id": default.get("primary_module_id", "MOD-01"),
                "support_module_ids": default.get("support_module_ids", ["MOD-07"]),
                "course_ids": default.get("course_ids", []),
                "focus": default.get("focus", "先确认顾客目标和必要安全信息。"),
                "stop_sales": default.get("stop_sales", False),
            }

    topic_primary = topics[0].get("module_id") if topics else None
    intent_primary = intent.get("primary_module_id")
    if not matched_intent and topic_primary:
        primary_module_id = topic_primary
    elif intent_primary == "DYNAMIC":
        primary_module_id = topic_primary or default.get("primary_module_id", "MOD-01")
    else:
        primary_module_id = intent_primary or topic_primary or default.get("primary_module_id", "MOD-01")

    support_module_ids = []
    if topic_primary and topic_primary != primary_module_id:
        support_module_ids.append(topic_primary)
    for topic in topics:
        support_module_ids.extend(topic.get("support_module_ids", []))
        if topic.get("module_id") != primary_module_id:
            support_module_ids.append(topic.get("module_id"))
    support_module_ids.extend(intent.get("support_module_ids", []))
    if primary_module_id != "MOD-07":
        support_module_ids.append("MOD-07")
    support_module_ids = [item for item in unique_items(support_module_ids) if item in MODULE_BY_ID and item != primary_module_id]

    course_ids = [*intent.get("course_ids", [])]
    knowledge_points = []
    for topic in topics:
        course_ids.extend(topic.get("course_ids", []))
        knowledge_points.extend(topic.get("knowledge_points", []))
    if not topics and not matched_intent:
        course_ids.extend(default.get("course_ids", []))
    if primary_module_id == "MOD-07" or intent.get("stop_sales"):
        course_ids.extend(["COURSE-SERVICE-SAFETY-001", "COURSE-COMPLIANCE-MEDICAL-001"])
    course_ids = [item for item in unique_items(course_ids) if item in COURSE_BY_ID]

    if intent.get("stop_sales"):
        method_step = "安全确认与停止分流"
    elif intent.get("id") in {"INTENT-PRICE", "INTENT-RESULT", "INTENT-COMPARISON", "INTENT-DECISION"}:
        method_step = "承接异议、依据回应并确认下一步"
    elif intent.get("id") == "INTENT-SUITABILITY":
        method_step = "安全确认后再解释选择"
    elif topics:
        method_step = "定位项目、补充必要信息并解释选择"
    else:
        method_step = "了解目标并完成问题定位"

    primary_module = MODULE_BY_ID.get(primary_module_id, {})
    support_modules = [MODULE_BY_ID[item] for item in support_module_ids]
    course_titles = [COURSE_BY_ID[item]["title"] for item in course_ids]
    return {
        "intent_id": intent.get("id", "INTENT-INFORMATION"),
        "intent_label": intent.get("label", "一般需求咨询"),
        "topic_labels": [topic.get("label", "") for topic in topics],
        "primary_module_id": primary_module_id,
        "primary_module": primary_module.get("title", "新客接待与需求洞察"),
        "support_module_ids": support_module_ids,
        "support_modules": [module.get("title", "") for module in support_modules],
        "required_course_ids": course_ids,
        "required_courses": course_titles,
        "knowledge_points": unique_items(knowledge_points)[:6],
        "focus": intent.get("focus", default.get("focus", "先确认顾客目标和必要安全信息。")),
        "recommended_next": (
            intent.get("recommended_next")
            if matched_intent and intent.get("recommended_next")
            else next((topic.get("recommended_next") for topic in topics if topic.get("recommended_next")), default.get("focus", "先确认顾客目标和必要安全信息。"))
        ),
        "method_step": method_step,
        "stop_sales": bool(intent.get("stop_sales")),
    }


def public_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": route.get("intent_label", "一般需求咨询"),
        "primary_module": route.get("primary_module", "新客接待与需求洞察"),
        "supporting_modules": route.get("support_modules", []),
        "knowledge_points": route.get("knowledge_points", [])[:4],
        "courses": route.get("required_courses", [])[:5],
        "method_step": route.get("method_step", "了解目标并完成问题定位"),
        "stop_sales": route.get("stop_sales", False),
    }


def route_context_block(route: dict[str, Any]) -> str:
    return json.dumps({
        "问题类型": route.get("intent_label"),
        "主要知识模块": route.get("primary_module"),
        "辅助知识模块": route.get("support_modules", []),
        "必须调用课程": route.get("required_courses", []),
        "回答重点": route.get("focus"),
        "项目或主题知识点": route.get("knowledge_points", []),
        "推荐下一步": route.get("recommended_next"),
        "是否停止销售推进": route.get("stop_sales", False),
    }, ensure_ascii=False)


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def text_terms(text: str) -> set[str]:
    value = clean_text(text).lower()
    terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", value))
    terms.update(value[i : i + 2] for i in range(len(value) - 1) if "\u4e00" <= value[i] <= "\u9fff" and "\u4e00" <= value[i + 1] <= "\u9fff")
    return terms


def related_course(doc: dict[str, Any]) -> dict[str, Any] | None:
    document_id = str(doc.get("document_id", ""))
    metadata = doc.get("metadata", {})
    if metadata.get("course_id") in COURSE_BY_ID:
        return COURSE_BY_ID[metadata["course_id"]]
    if document_id in COURSE_BY_KNOWLEDGE_ID:
        return COURSE_BY_KNOWLEDGE_ID[document_id]
    candidates = SOURCE_TO_COURSES.get(str(metadata.get("source_id", "")), [])
    if not candidates:
        module_id = DOMAIN_TO_MODULE.get(str(metadata.get("domain", "")))
        candidates = [course for course in LEARNING_CATALOG["courses"] if course.get("module_id") == module_id]
    if not candidates:
        return None
    doc_terms = text_terms(f"{metadata.get('title', '')} {doc.get('text', '')}")
    return max(
        candidates,
        key=lambda course: len(doc_terms & text_terms(json.dumps(course, ensure_ascii=False))),
    )


def retrieve(query: str, limit: int = 8, domain: str | None = None, route: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    query = clean_text(query)
    if not query:
        return []
    q_terms = text_terms(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    required_course_ids = set((route or {}).get("required_course_ids", []))
    routed_module_ids = {
        (route or {}).get("primary_module_id"),
        *((route or {}).get("support_module_ids", [])),
    }
    routed_module_ids.discard(None)
    for doc in RAG_DOCUMENTS:
        metadata = doc.get("metadata", {})
        # 原始资料保留用于审计，但不直接进入机器人上下文；机器人只使用已重写的
        # 课程、结构化卡片、异议案例和安全规则，避免旧版医疗化/绝对化话术复现。
        if metadata.get("doc_type") == "source":
            continue
        if domain and metadata.get("domain") not in {domain, "safety", "objections"}:
            continue
        if route and metadata.get("doc_type") == "course_section":
            if metadata.get("module_id") not in routed_module_ids and metadata.get("course_id") not in required_course_ids:
                continue
        doc_text = clean_text(doc.get("text", ""))
        d_terms = text_terms(doc_text)
        overlap = len(q_terms & d_terms)
        phrase = 1.0 if query.lower() in doc_text.lower() else 0.0
        title_bonus = len(q_terms & text_terms(metadata.get("title", ""))) * 0.7
        base_score = overlap + phrase * 5 + title_bonus
        course_bonus = 2.5 if metadata.get("doc_type") == "course_section" else 0.0
        route_bonus = 0.0
        if metadata.get("course_id") in required_course_ids:
            route_bonus += 10.0
        if metadata.get("module_id") in routed_module_ids:
            route_bonus += 3.0
        score = base_score + course_bonus + route_bonus
        if base_score > 0 or route_bonus > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: (-item[0], item[1].get("document_id", "")))
    selected = []
    per_course: dict[str, int] = {}
    selected_ids = set()
    if route:
        for required_course_id in route.get("required_course_ids", []):
            match = next((item for item in scored if item[1].get("metadata", {}).get("course_id") == required_course_id), None)
            if not match:
                continue
            score, doc = match
            selected.append({**doc, "retrieval_score": round(score, 2)})
            selected_ids.add(doc.get("document_id"))
            per_course[required_course_id] = 1
            if len(selected) >= limit:
                return selected
    for score, doc in scored:
        if doc.get("document_id") in selected_ids:
            continue
        course_id = str(doc.get("metadata", {}).get("course_id") or doc.get("document_id", ""))
        if per_course.get(course_id, 0) >= 2:
            continue
        selected.append({**doc, "retrieval_score": round(score, 2)})
        per_course[course_id] = per_course.get(course_id, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    persona = scenario.get("persona", {})
    return {
        "id": scenario.get("id"),
        "domain": scenario.get("domain"),
        "age": persona.get("age"),
        "gender": persona.get("gender"),
        "occupation": persona.get("occupation"),
        "style": persona.get("style"),
        "goal": persona.get("goal"),
        "opening": scenario.get("opening"),
    }


def public_doc_title(doc: dict[str, Any]) -> str:
    document_id = str(doc.get("document_id", ""))
    course = related_course(doc)
    if course:
        return course["title"]
    metadata = doc.get("metadata", {})
    domain = metadata.get("domain", "")
    if document_id.startswith("OB-"):
        title = clean_text(metadata.get("title", ""))
        return f"常见顾客异议：{title}" if title else "常见顾客异议处理"
    if document_id == "COMPLIANCE-MEDICAL-001":
        return PUBLIC_TITLE_BY_ID.get(document_id, "医疗与营销安全底线")
    return DOMAIN_LABELS.get(domain, "企业培训知识")


def public_doc_category(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata", {})
    doc_type = metadata.get("doc_type", "")
    if doc_type == "objection":
        return "话术案例"
    if doc_type in {"platform_policy", "safety"} or metadata.get("domain") == "safety":
        return "安全规则"
    if doc_type == "source":
        return "企业知识"
    return "标准课程"


def public_citations(docs: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen = set()
    citations = []
    for doc in docs:
        label = public_doc_title(doc)
        if label in seen:
            continue
        seen.add(label)
        course = related_course(doc)
        module = MODULE_BY_ID.get(course.get("module_id"), {}) if course else {}
        citations.append({
            "label": label,
            "course_id": course.get("id", "") if course else "",
            "category": public_doc_category(doc),
            "module": module.get("short_name", ""),
            "chapter": course.get("group_title", "") if course else "",
        })
    return citations


def public_retrieved(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    seen = set()
    for doc in docs:
        course = related_course(doc)
        title = course.get("title") if course else public_doc_title(doc)
        if title in seen:
            continue
        seen.add(title)
        module = MODULE_BY_ID.get(course.get("module_id"), {}) if course else {}
        items.append({
            "course_id": course.get("id", "") if course else "",
            "title": title,
            "category": public_doc_category(doc),
            "module": module.get("short_name", ""),
            "chapter": course.get("group_title", "") if course else "",
        })
    return items


def sanitize_public_string(value: str) -> str:
    value = re.sub(r"\bSRC-\d+(?:\s*,\s*SRC-\d+)*\b", "企业知识库", value)
    value = re.sub(r"\b(?:FLOW|PROD|OP|KNOW|SERVICE|OPS|COMPLIANCE|OB|SCN)-[A-Z0-9-]+\b", "相关课程", value)
    value = re.sub(r"(?:document_id|source_id)\s*=\s*[^\s，。；]+", "", value, flags=re.I)
    value = re.sub(r"[^，。；：\n]{1,80}\.(?:docx?|pptx?|xlsx?|xls|pdf|mp4)\b", "企业培训资料", value, flags=re.I)
    value = re.sub(r"\bCHUNK-\d+\b", "", value)
    return clean_text(value)


def sanitize_public_result(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_public_string(value)
    if isinstance(value, list):
        return [sanitize_public_result(item) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_public_result(item)
            for key, item in value.items()
            if key not in {"safety_filter_matches", "safety_filter_triggered"}
        }
    return value


ASSESSMENT_SPECIFIC_ADVICE = re.compile(r"(?:古方|口服|注射|用药|药品|剂量|停药|隔天一次|每天\s*\d+\s*次)", re.I)


def sanitize_assessment_advice(result: dict[str, Any]) -> dict[str, Any]:
    """Keep scoring evidence intact while removing unverified product or usage advice."""
    if not isinstance(result, dict):
        return result
    for dimension in result.get("dimension_scores", []):
        if isinstance(dimension, dict) and ASSESSMENT_SPECIFIC_ADVICE.search(clean_text(dimension.get("comment"))):
            dimension["comment"] = "员工尚未把顾客顾虑转化为可执行的下一步。建议先澄清时间、预算和服务偏好，再给出门店当前已核验且符合安全边界的选择。"
    improvements = result.get("improvements")
    if isinstance(improvements, list):
        result["improvements"] = [
            "不要替顾客直接选择具体产品或使用安排；先核验适用条件和门店当前标准，再提供非医疗、可选择的下一步。"
            if ASSESSMENT_SPECIFIC_ADVICE.search(clean_text(item)) else item
            for item in improvements
        ]
    if ASSESSMENT_SPECIFIC_ADVICE.search(clean_text(result.get("summary"))):
        result["summary"] = "本轮需要加强需求分析和个性化表达。后续重点练习在不承诺结果、不擅自补充具体产品或使用安排的前提下，把顾客顾虑转化为可执行的服务下一步。"
    return result


def context_block(docs: list[dict[str, Any]], max_docs: int | None = None, max_chars_per_doc: int | None = None) -> str:
    """Render a bounded knowledge context for model prompts.

    Retrieval keeps the full evidence set for citations and regression checks, but
    interactive prompts should remain compact enough for reliable multi-turn API
    responses.  Truncation happens only at prompt rendering time.
    """
    if max_docs is not None:
        docs = docs[:max_docs]
    blocks = []
    for index, doc in enumerate(docs, start=1):
        text = clean_text(doc.get("text", ""))
        if max_chars_per_doc is not None and len(text) > max_chars_per_doc:
            text = text[:max_chars_per_doc].rstrip() + "…"
        blocks.append(
            f"[知识内容{index}] 主题={public_doc_title(doc)}；类别={public_doc_category(doc)}\n"
            f"{text}"
        )
    return "\n\n".join(blocks)


SAFETY_POLICY = """安全边界：不做诊断、处方、剂量建议或停药建议；不承诺治愈、根治、百分百有效、固定减重斤数或不反弹；不使用恐吓、羞辱身材、隐瞒病史、贬低医院/竞品来成交。出现胸痛、呼吸困难、晕厥、突发剧痛、进行性麻木无力、发热红肿、外伤后明显受限等红旗信号时，停止营销和操作，建议由有资质人员/医疗机构评估。"""

METHODOLOGY_POLICY = """

统一接待与回答方法（必须执行）：
1. 先读取输入中的“方法路由”。它已经根据知识库确定了问题类型、主要模块、辅助模块、必须调用课程和安全优先级；不得自行换成无关项目或凭常识补充公司标准。
2. 先过安全闸门。路由要求停止销售时，只做风险承接、必要问询、停止/升级/转介和记录，不继续项目介绍、成交或产品推荐。
3. 正常回答依次完成：承接当前问题 → 只补一个必要信息 → 使用指定课程回应 → 说明必要边界或待核验点 → 给一个可执行下一步并确认顾客意愿。
4. 只回答顾客当前最关心的一件事。不要一次倾倒全部知识，不用模块名或内部分析代替对顾客说的话。
5. 推荐必须来自顾客已表达的目标、时间、预算、舒适度和风险信息；信息不足时先提问，不直接推荐具体项目、次数、产品或价格。
6. 动态价格、活动、次数和门店政策必须先确认城市、门店、项目、日期及当前版本；无法确认就明确待核验。
"""

HIGH_RISK_CLAIM_PATTERNS = [
    r"自动诊疗",
    r"替代手术",
    r"保证(?:效果|结果|瘦|减重)",
    r"(?:治愈|根治|治疗|治好).{0,8}(?:疾病|颈椎病|糖尿病|三高|脂肪肝|炎症)",
    r"(?:有效|能够|可以|会).{0,10}(?:治疗|治好|根治|改善糖尿病|改善三高|改善脂肪肝|提高免疫力|增强免疫力)",
    r"(?:固定|保证).{0,8}(?:减重|减肥).{0,8}(?:斤|公斤)",
    r"不反弹",
    r"百分之百|百分百|100%",
    r"白血球.{0,10}(?:增加|提高)",
    r"(?:宫寒|卵巢|肾虚).{0,12}(?:受孕|衰老|疾病|治疗)",
    r"国家药监局.{0,20}(?:批准|认证)",
    r"单次治疗|后续疗程|按疗程|进入疗程",
    r"压迫.{0,8}(?:血管|神经)",
    r"(?:可能)?涉及.{0,6}(?:神经|血管)",
    r"脑部.{0,8}供血|供血供氧.{0,8}不足",
    r"(?:检查|查体).{0,12}(?:僵硬程度|结节|体征)",
    r"(?:一定|肯定|保证).{0,8}(?:有效|缓解|改善)",
]


def unsafe_claim_hits(text: str) -> list[str]:
    hits = []
    for pattern in HIGH_RISK_CLAIM_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.I):
            prefix = text[max(0, match.start() - 14):match.start()]
            if re.search(r"(?:不能|不可|不应|无法|不得|不会|不做|避免|禁止|拒绝).{0,10}$", prefix):
                continue
            hits.append(pattern)
            break
    return hits


def safety_filter(result: dict[str, Any], mode: str, user_text: str = "", route: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prevent legacy source claims from becoming unqualified model advice."""
    if not isinstance(result, dict):
        return result
    route = route or {}
    feedback = result.get("feedback") if isinstance(result.get("feedback"), dict) else {}
    fields = [
        clean_text(result.get("answer")),
        clean_text(result.get("recommended_action")),
        clean_text(result.get("suggested_reply")),
        clean_text(feedback.get("issue")),
        clean_text(feedback.get("why")),
        clean_text(feedback.get("suggested_reply")),
        clean_text(feedback.get("next_goal")),
    ]
    combined = " ".join(fields)
    hits = unsafe_claim_hits(combined)
    user_hits = unsafe_claim_hits(user_text) if mode == "training" else []
    if user_hits:
        hits.extend(item for item in user_hits if item not in hits)
    if mode == "qa" and re.search(r"敏感肌|皮肤过敏|容易过敏|医美恢复", user_text, flags=re.I):
        result["answer"] = "不能只凭‘敏感肌’三个字判断能不能做。先确认目前有没有持续泛红、刺痛、破损、渗出、明显痘痘炎症或过敏发作，以及近期是否做过医美、刷酸、激光或使用强刺激产品。存在这些情况时先不操作，并建议由皮肤科或原医疗机构确认；状态稳定时，也要再核对具体项目、成分、设备禁忌和门店当前SOP，先做小范围感受测试，过程中一旦刺痛、灼热或泛红加重立即停止。降低次数不能替代适用性判断。"
        result["uncertainties"] = ["需要确认当前皮肤是否处于急性敏感或治疗恢复期。", "需要核对具体产品成分、设备型号和当前门店SOP。"]
        result["recommended_action"] = "先完成皮肤状态、过敏史、近期项目史和成分核对；无法确认时不操作。"
        result["safety_filter_triggered"] = True
        return result
    if mode == "qa" and re.search(r"GLP-1|glp-1|司美|减肥针|处方|药品|减肥药|口服片|剂量|停药|换药|怎么用", user_text, flags=re.I):
        result["answer"] = "您问的是药品适用性、用法和剂量，这些必须依据具体药品的当前说明书和医生处方，门店不能只凭体重、疾病名称或聊天给剂量，也不能建议开始、停用或更换药物。请先确认具体药名、剂型、开药医生、正在使用的其他药物和当前不适，再由开药医生或药师核实。"
        result["uncertainties"] = ["需要确认具体药品身份、处方、合并用药和当前症状。"]
        result["recommended_action"] = "暂停具体产品或剂量建议，携带药品包装和用药记录咨询开药医生或药师。"
        result["safety_filter_triggered"] = True
        return result
    if mode == "qa" and re.search(r"孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高", user_text, flags=re.I):
        result["answer"] = "这类情况不能仅凭聊天直接判断‘可以做’。先暂停项目或产品推荐，确认具体年龄/阶段、疾病与用药、当前症状和产品或设备说明书，再由有资质的医生、药师或相应专业人员确认。门店不能通过降低能量、缩短时间或减少次数来替代适用性评估。"
        result["uncertainties"] = ["需要更具体的健康信息和当前用药信息。", "需要核对产品标签、设备说明书和门店当前合规版本。"]
        result["recommended_action"] = "核实信息并转有资质人员确认；确认前不操作、不销售具体方案。"
        result["safety_filter_triggered"] = True
        return result
    if mode == "qa" and route.get("stop_sales"):
        follow_up = bool(re.search(r"怎么办|现在|下一步|那我|接下来", user_text, flags=re.I))
        result["answer"] = (
            "现在先停止体验和销售沟通，不要自行判断原因。若胸痛、呼吸困难、晕厥、明显出冷汗或进行性麻木无力正在发生、持续或加重，请尽快联系急救或前往医疗机构；情况稳定后再由门店负责人记录并跟进。"
            if follow_up
            else "您提到的情况需要先确认安全，今天先不要做项目，也不要继续产品推荐。请告诉我症状从什么时候开始、是否正在加重，以及有没有胸痛、呼吸困难、晕厥或进行性麻木无力；症状明显、持续或加重时，请尽快联系急救或前往医疗机构。"
        )
        result["uncertainties"] = ["需要确认症状开始时间、程度、变化和伴随情况。"]
        result["recommended_action"] = "停止销售推进，完成风险问询、负责人升级和必要的医疗分流。"
        result["safety_filter_triggered"] = True
        return result
    if not hits:
        return result
    if mode == "qa":
        module_ids = {route.get("primary_module_id"), *route.get("support_module_ids", [])}
        if route.get("stop_sales"):
            result["answer"] = "您提到的情况需要先确认安全。今天先暂停项目、操作和产品推荐，请告诉我症状从什么时候开始、是否正在加重，以及有没有胸痛、呼吸困难、晕厥、进行性麻木无力等情况。门店不能判断病因；如果症状明显、持续或加重，建议及时由医疗机构评估。"
            result["uncertainties"] = ["需要确认症状开始时间、程度、变化和伴随情况。"]
            result["recommended_action"] = "停止销售推进，完成风险问询、负责人升级和必要的医疗分流。"
        elif "MOD-05" in module_ids or re.search(r"减肥|减重|体重|瘦|斤|反弹", user_text, flags=re.I):
            result["answer"] = "我理解您希望尽快看到并保持变化，但不能承诺一个月固定减重多少，也不能保证永不反弹。每个人的体重趋势会受到饮食、活动、睡眠、压力、既往经历和健康情况影响。我们先把这些情况问清楚，再把目标拆成可观察、能执行的阶段指标，按统一条件持续复盘。"
            result["uncertainties"] = ["需要确认当前体重趋势、生活节奏、既往减重经历和健康风险。"]
            result["recommended_action"] = "先完成体重管理需求与风险问询，再确定一到两个阶段指标和下一周可执行动作。"
        elif "MOD-04" in module_ids:
            result["answer"] = "是否适合不能只凭一个肤质标签判断。先确认目前有没有泛红、刺痛、破损、渗出或过敏发作，以及近期是否做过医美、刷酸或使用强刺激产品；存在这些情况时先不操作。状态稳定时也要核对具体项目、成分、禁忌和当前SOP，过程中任何刺痛、灼热或泛红加重都要立即停止。"
            result["uncertainties"] = ["需要核对当前皮肤状态、过敏史、近期项目史和具体成分。"]
            result["recommended_action"] = "先完成肤况和项目适用性确认；无法确认时不操作。"
        elif re.search(r"一次|几次|多久|有效|见效", user_text, flags=re.I):
            result["answer"] = "不能承诺做一次、固定次数或固定时间就一定有效。先确认您最想改善的具体指标和既往情况，体验前记录同一项动作、主观感受或合规数据，体验后再按相同条件对照。当次变化只代表当次观察，长期结果需要阶段复盘，也存在个体差异。"
            result["uncertainties"] = ["需要确认具体项目、顾客目标和用于判断变化的指标。"]
            result["recommended_action"] = "先确定一个可观察指标和安全信息，再决定是否体验及何时复盘。"
        else:
            result["answer"] = "这个问题不能用诊断、治疗或保证结果的方式回答。先确认您最想改善的目标、持续时间、既往情况和必要安全信息；目前只能按已核验的门店流程说明体验方式、可能感受和限制，无法确认的参数、适用性或结果需要进一步核验。"
            result["uncertainties"] = ["需要确认具体项目、顾客目标和安全信息。"]
            result["recommended_action"] = route.get("recommended_next", "先补齐必要信息，再按当前课程和门店标准给出选择。")
    elif mode == "training":
        result["feedback"] = result.get("feedback") or {}
        user_hits = unsafe_claim_hits(user_text)
        if user_hits:
            result["feedback"]["level"] = "critical"
            result["feedback"]["issue"] = "员工原话包含医疗化判断或结果承诺，需要立即改成风险问询和服务边界说明。"
        result["feedback"]["why"] = "门店员工不能判断病因、解释为血管或神经受压，也不能使用治疗、疗程或固定效果承诺。先确认风险，再说明门店仅提供非医疗性质的服务体验。"
        module_ids = {route.get("primary_module_id"), *route.get("support_module_ids", [])}
        if route.get("stop_sales"):
            suggested_reply = "您提到的不适需要先确认安全。今天先暂停项目和推荐，请告诉我症状从什么时候开始、是否正在加重；如果症状明显或伴随胸痛、呼吸困难、晕厥、进行性麻木无力等情况，建议及时医疗评估。"
        elif "MOD-05" in module_ids:
            suggested_reply = "我理解您希望尽快看到变化，但我不能承诺固定斤数或不反弹。先了解您的体重趋势、饮食睡眠、活动和既往减重经历，再把目标拆成能执行的阶段指标。"
        elif "MOD-04" in module_ids:
            suggested_reply = "我先确认您目前有没有泛红、刺痛、破损或过敏发作，以及近期是否做过医美或使用强刺激产品；没有完成适用性确认前，我不能直接说一定能做。"
        elif "MOD-03" in module_ids:
            suggested_reply = "我理解您担心温度。开始前先确认皮肤、怕热和既往情况，过程中会结合设备读数持续询问感受；任何过热、疼痛、头晕或不舒服都要立即暂停。"
        else:
            suggested_reply = "我理解您想改善目前的不适，但我不能判断病因或承诺结果。先确认位置、持续时间、最近变化和伴随情况；有明显风险时先做医疗评估，确认适合后再说明门店能提供的非医疗体验。"
        result["feedback"]["suggested_reply"] = suggested_reply
        result["feedback"]["next_goal"] = "继续完成风险问询，并用非医疗化语言说明服务边界。"
    result["safety_filter_triggered"] = True
    result["safety_filter_matches"] = hits
    return result


def with_safety_doc(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policy = next((doc for doc in RAG_DOCUMENTS if doc.get("document_id") == "COMPLIANCE-MEDICAL-001"), None)
    if policy and not any(doc.get("document_id") == policy.get("document_id") for doc in docs):
        return [*docs, policy]
    return docs


LIMITED_CUSTOMER_POLICY = """
顾客角色认知边界（最高优先级）：
1. 顾客只知道自己的困扰、感受、生活情况和真实顾虑；对门店项目最多只听过一个模糊名称，不知道专业原理、成分、设备、适用标准、禁忌、操作流程或员工问诊方法。
2. 只回答员工最新提出的问题；员工没有问到的个人信息不要主动成批透露。缺少设定的信息就自然说“不太清楚、没留意、说不上来”，不得用专业知识补全。
3. 绝不替员工做需求分析、风险筛查或服务建议；不得反过来询问员工的病史、医美史、过敏史、用药或护肤品，也不得指导员工下一步应该问什么。
4. 每轮只表达一个事实、感受或顾虑，通常 15—60 个汉字；最多问一个符合普通顾客认知的问题，不能连续盘问或列检查清单。
5. 始终记住自己是来咨询的顾客。员工答错时可以不满意、疑惑或要求重新说明，但不能变成咨询师、教练、医生或产品专家。
6. 不主动使用“适用性确认、专业评估、医疗评估、红旗、禁忌、SOP、成分核对、设备型号、阶段指标、复盘”等专业词。若员工使用这些词，只按普通顾客能理解的方式回应。
7. 员工只给出简单否定、空泛肯定（例如“有的”“可以”“好的”）或答非所问时，这不算已经回答顾客。先围绕顾客上一问追问具体方法、项目或安排，不要突然跳到价格、成分或另一个新话题。只有员工已经给出与当前问题相关的实际说明后，才进入下一条顾虑。
"""


TRAIN_SYSTEM = """你是美容、瘦身门店的员工训练教练。你要同时完成两件事：让顾客角色的对话自然真实，并在每轮后指出员工一个最重要的改进点。

只使用给定知识库作为专业依据。资料中可能存在旧版本、营销表述或需要核验的医学内容，不得擅自把它们改写成确定性承诺。""" + SAFETY_POLICY + METHODOLOGY_POLICY + """

训练模式输出严格 JSON，不要 Markdown，不要额外解释：
{"customer_reply":"顾客下一句话","feedback":{"level":"good|needs_work|critical","issue":"引用员工原话并指出一个最重要的问题或做得好的地方","why":"说明当前处于哪个接待节点、应调用什么知识和为什么","method_step":"本轮应执行的方法节点","knowledge_focus":"本轮主要知识重点","suggested_reply":"严格按方法路由生成的一句自然话术","next_goal":"下一轮只练一个目标"},"citations":[]}
feedback 必须引用员工刚刚说的话，不能泛泛而谈；必须检查员工是否先安全后业务、是否回答当前问题、是否使用正确知识模块、是否给出可执行下一步。顾客不知道内部规则，不要把隐藏场景设定和评分标准泄露给员工。
customer_reply 字段和 feedback 字段必须严格隔离：feedback 可以使用专业知识，customer_reply 必须完全遵守下面的顾客角色认知边界，绝不能把教练知识说成顾客的话。""" + LIMITED_CUSTOMER_POLICY


TEST_TURN_SYSTEM = """你是美容、瘦身门店实战考核中的模拟顾客，不是培训教练、客服助手或评分员。

对话规则：
1. 只回应员工最新一句话，每轮用顾客口吻回复 1—3 句；不能评价员工、讲方法、给提示、总结知识或暴露评分点。
2. 开场白已由系统展示，后续绝不重复开场白，也不原样重复之前说过的话。
3. 根据员工实际提问，每轮最多自然透露一个尚未透露的背景、顾虑或异议；员工没有问到时不要主动把隐藏信息全部说出。
4. 如果员工答非所问，继续以顾客身份追问原问题；如果员工给出危险承诺，以顾客身份表示疑惑或不放心，但不要替员工说出标准答案。
5. 不得出现“考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该”等幕后词语。

严格输出 JSON，不要 Markdown：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。""" + LIMITED_CUSTOMER_POLICY


QA_SYSTEM = """你是企业培训知识库中的专业顾客接待助手。你面对的是顾客，因此答案必须是一段可以直接对顾客说的话，而不是知识摘要、检索报告或员工培训分析。只能基于方法路由和检索资料，不能把知识库之外的猜测说成公司标准。

回答要求：这是连续对话，必须结合最近的顾客问题和你的上一轮回答理解“这个、那、它、怎么办”等指代，但只回答顾客当前这一问。先直接承接顾客当前问题；如果缺少决定答案的关键信息，只问一个最必要的问题；再给已核验的事实、流程或边界；最后给一个可执行下一步。通常控制在80—220个汉字，复杂安全问题可适当增加。不要机械重复上一轮答案，不要重复相同免责声明，不要罗列无关知识。

回答结构严格 JSON：{"answer":"可直接对顾客说的完整回答","uncertainties":["确实需要核验的点，没有则为空数组"],"citations":[],"recommended_action":"一个明确、可执行的下一步"}。如果资料不足，明确说资料不足并说明要补充什么；如果涉及医疗、药品、孕期、儿童、慢病、服务后异常或红旗症状，优先安全分流。""" + SAFETY_POLICY + METHODOLOGY_POLICY


ASSESS_SYSTEM = """你是企业培训考核官。只在对话结束后评分，不再扮演顾客，也不继续对话。

评分边界：
1. history 中 role=user 的内容才是员工原话；role=assistant 是模拟顾客原话，绝不能把顾客说过的话算成员工能力或员工错误。
2. 必须严格按评分表的 7 个维度逐项评分，dimension_scores 恰好 7 项，id、name、max_score 与评分表完全一致，不得缺项、加项或改权重。
3. 每个维度的 evidence 必须引用员工原话或明确写“对话中未体现”；未体现的能力不得凭空给高分。
4. total_score 必须等于 7 个 score 之和；先算维度分，再应用关键失败项的 score_cap。
5. 只评价本次对话已经发生的内容。建议写成下一轮训练动作，不要虚构员工已经说过的话，不要替员工补充产品、药品、剂量、用法或频次。
6. 输出内容必须是考核报告，不能输出新的顾客回复或继续向员工提问。

评分时检查员工是否遵守统一方法：先安全后业务、回答当前问题、调用正确知识、只补必要问题、说明边界并给出正确下一步。输出严格 JSON：
{"total_score":0,"dimension_scores":[{"id":"D1","name":"...","score":0,"max_score":10,"evidence":"对话证据","comment":"评价"}],"critical_failures":[{"code":"CF-xx","reason":"...","evidence":"...","score_cap":59}],"strengths":["..."],"improvements":["..."],"next_training_scene":"SCN-...","summary":"..."}
先按各维度评分，再应用关键失败封顶规则；没有关键失败时 critical_failures 必须为空。D3评价是否使用正确课程知识，D4评价是否把顾客问题定位到正确模块并形成个性化下一步，D5评价是否按承接—澄清—回应—选择—确认处理异议。不得替员工补充具体产品、口服/注射方案、剂量、用法或频次；员工没有给出具体方案时，只评价该能力缺失，并建议继续澄清需求、核验门店标准。""" + SAFETY_POLICY + METHODOLOGY_POLICY


PUBLIC_OUTPUT_POLICY = """

用户界面输出规则（高优先级）：
1. 只使用员工和顾客能理解的课程名称，不展示或提及原始文件名、文件扩展名、来源编号、document_id、source_id、CHUNK、内部权威等级或技术检索字段。
2. 不要说“根据某某.docx/PPT/PDF/视频文件”；可以说“根据接待标准”“根据安全规则”“根据体重管理课程”。
3. 语言要像一位专业、清楚、温和的培训教练，避免内部术语堆砌。
4. 如输出 citations，只允许格式 [{"label":"员工可理解的知识主题"}]，不得包含任何内部编号。
5. 门店服务统一使用“体验、基础观察、顾客感受、阶段复盘”等非医疗表述；不得把服务称为“治疗、疗程、检查”，不得推断血管、神经、供血供氧等医学原因，也不得承诺固定效果。
"""

TRAIN_SYSTEM += PUBLIC_OUTPUT_POLICY + "\n训练模式的 citations 固定返回空数组。"
QA_SYSTEM += PUBLIC_OUTPUT_POLICY
ASSESS_SYSTEM += PUBLIC_OUTPUT_POLICY


def extract_json(content: str) -> dict[str, Any] | None:
    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I | re.S).strip()
    try:
        value = json.loads(content)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def call_model(system: str, messages: list[dict[str, str]], model: str, api_key: str, temperature: float = 0.4, max_tokens: int = 1800) -> tuple[str, dict[str, Any]]:
    if MOCK_MODE or not api_key:
        raise RuntimeError("mock_or_missing_key")
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, *messages],
        "temperature": temperature,
        "top_p": 0.7,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    if model.startswith("Qwen/Qwen3") or "DeepSeek-V3.2" in model or model.startswith("Pro/zai-org/GLM-5"):
        payload["enable_thinking"] = False
    request = urllib.request.Request(
        SILICONFLOW_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"SiliconFlow API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SiliconFlow network error: {exc.reason}") from exc
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content, {"model": body.get("model", model), "usage": body.get("usage", {})}


def mock_response(mode: str, action: str, message: str, scenario: dict[str, Any] | None, history: list[dict[str, str]], docs: list[dict[str, Any]]) -> dict[str, Any]:
    if mode == "training":
        weak = not any(word in message for word in ["了解", "多久", "哪里", "感受", "目标", "担心", "方便", "预算", "疼", "病史"])
        return {
            "customer_reply": test_fallback_reply(scenario, history, message),
            "feedback": {
                "level": "needs_work" if weak else "good",
                "issue": "还没有围绕顾客的目标、症状时间和影响做追问。" if weak else "你有继续追问顾客目标，方向正确。",
                "why": "新客接待要先完成需求分析，再进入项目介绍；不能只背项目卖点。",
                "method_step": "了解目标并完成问题定位",
                "knowledge_focus": "目标、持续时间、影响和安全信息",
                "suggested_reply": "我先了解一下：这种紧和头痛大概多久了？什么情况下更明显？对工作或睡眠有影响吗？",
                "next_goal": "下一轮先问清目标、持续时间和影响，再决定是否介绍项目。",
            },
            "citations": [{"document_id": d.get("document_id"), "source_id": d.get("metadata", {}).get("source_id"), "title": d.get("metadata", {}).get("title")} for d in docs[:2]],
        }
    if mode == "test" and action == "turn":
        reply = test_fallback_reply(scenario, history, message)
        return {"reply": reply, "emotion": "hesitant", "should_continue": True}
    return {
        "answer": "当前是本地演示模式。已经检索到相关资料，但尚未调用真实模型。配置 SiliconFlow API Key 后，可生成基于这些资料的正式回答。",
        "uncertainties": ["请以当前门店价格、项目标签和合规版本为准。"],
        "citations": [{"document_id": d.get("document_id"), "source_id": d.get("metadata", {}).get("source_id"), "title": d.get("metadata", {}).get("title")} for d in docs[:3]],
        "recommended_action": "先核对门店当前版本的价格、频次和适用边界。",
    }


def mock_qa_response(message: str, route: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Provide a useful, deterministic QA answer when no provider key is configured."""
    intent_id = route.get("intent_id")
    module_ids = {route.get("primary_module_id"), *route.get("support_module_ids", [])}
    if intent_id == "INTENT-RESULT" or re.search(r"一次|几次|多久|有效|见效|保证|反弹", message, re.I):
        answer = "我理解您希望尽快看到变化，但不能承诺一次、固定时间或固定结果，也不能保证不反弹。先确认您最想改善的指标和既往情况，再按相同条件记录并做阶段观察；长期变化还会受到生活方式和个体差异影响。"
        uncertainties = ["需要确认具体项目、顾客目标和用于判断变化的指标。"]
        recommended_action = "先确定一个可观察指标和必要安全信息，再决定是否体验及何时复盘。"
    elif intent_id == "INTENT-COMPARISON":
        answer = "不同项目不能只按名称判断谁更好，需要围绕您想改善的问题、可接受的体验、时间安排和必要安全信息来比较。请先告诉我您正在比较哪两个项目，以及最在意效果感受、时间还是预算中的哪一点。"
        uncertainties = ["需要确认正在比较的具体项目和最重要的选择标准。"]
        recommended_action = "先补齐比较对象和选择标准，再按当前课程与门店有效版本逐项说明。"
    elif "MOD-05" in module_ids:
        answer = "体重管理不能只凭一个数字直接推荐方案，也不能承诺固定减重斤数。先了解当前体重趋势、饮食、活动、睡眠、既往经历和健康情况，再把目标拆成可观察、能执行的阶段指标。"
        uncertainties = ["需要确认当前体重趋势、生活节奏、既往经历和必要健康信息。"]
        recommended_action = "先完成需求与风险问询，再确定一到两个阶段指标。"
    elif "MOD-04" in module_ids:
        answer = "是否适合不能只凭一个肤质标签判断。先确认当前是否有泛红、刺痛、破损、渗出或过敏发作，以及近期是否做过医美、刷酸、激光或使用强刺激产品；无法确认时先不操作。"
        uncertainties = ["需要确认当前皮肤状态、过敏史、近期项目史和具体成分。"]
        recommended_action = "先完成肤况和项目适用性确认，再说明可选服务。"
    else:
        focus = clean_text(route.get("focus")) or "先确认顾客目标和必要安全信息。"
        answer = f"我先回答您当前最关心的问题：{focus} 目前还不能只凭这一句话直接推荐项目、次数或效果。请再告诉我具体想改善什么，以及这种情况大概持续多久。"
        uncertainties = ["需要确认具体目标、持续时间和必要安全信息。"]
        recommended_action = clean_text(route.get("recommended_next")) or "先补充一个必要信息，再确认下一步。"
    return {
        "answer": answer,
        "uncertainties": uncertainties,
        "citations": [
            {"document_id": item.get("document_id"), "title": item.get("metadata", {}).get("title")}
            for item in docs[:3]
        ],
        "recommended_action": recommended_action,
    }


def scenario_by_id(scenario_id: str | None) -> dict[str, Any]:
    if scenario_id:
        for item in SCENARIOS:
            if item.get("id") == scenario_id:
                return item
    return SCENARIOS[0]


def customer_turn_context(scenario: dict[str, Any] | None) -> dict[str, Any]:
    """Only expose facts a simulated customer may know; scoring rules stay assessor-only."""
    scenario = scenario or {}
    persona = scenario.get("persona") if isinstance(scenario.get("persona"), dict) else {}
    return {
        "persona": {
            key: persona.get(key)
            for key in ("age", "gender", "occupation", "style", "goal", "risk", "knowledge_level")
            if persona.get(key) not in {None, ""}
        },
        "hidden_objections": list(scenario.get("hidden_objections") or []),
    }


def clean_dialogue_history(history: list[dict[str, Any]], limit: int = 7) -> list[dict[str, str]]:
    cleaned = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = clean_text(item.get("content", ""))
        if content:
            cleaned.append({"role": item["role"], "content": content})
    return cleaned[-limit:]


def qa_context_query(message: str, history: list[dict[str, str]]) -> str:
    """Use prior customer questions only when the latest QA turn depends on context."""
    message = clean_text(message)
    contextual = bool(
        re.search(r"^(?:那|这个|这种|它|刚才|如果|那么|可是|但是)", message, re.I)
        or re.fullmatch(r"(?:那我|我)?(?:现在|接下来)?(?:应该|该)?(?:怎么办|做什么)(?:呢)?[？?]?", message, re.I)
        or re.fullmatch(r"(?:可以吗|为什么|多少钱|多少|多久|呢)[？?]?", message, re.I)
    )
    if not contextual:
        return message
    prior_questions = [item["content"] for item in history if item.get("role") == "user"][-3:]
    return clean_text(" ".join([*prior_questions, message]))


TEST_INTERNAL_MARKERS = re.compile(r"考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练", re.I)
CUSTOMER_ROLE_DRIFT_MARKERS = re.compile(
    r"适用性确认|专业评估|医疗评估|红旗|禁忌|SOP|成分核对|设备型号|阶段指标|复盘|"
    r"治疗史|特殊护肤品|强刺激产品|作用原理|工作原理|操作流程|测温|设备参数|产品机制|"
    r"(?:建议|请)您|我建议(?:你|您)|你(?:应该|需要).{0,12}(?:询问|确认|了解|评估|说明)|"
    r"您.{0,18}(?:有没有|是否|做过|用过|最近一次|病史|过敏史)",
    re.I,
)


CUSTOMER_VAGUE_EMPLOYEE_REPLY = re.compile(
    r"^(?:有|有的|有办法|有相关项目|可以|可以的|能做|好的|好|是的|对|对的|没问题|了解|知道)"
    r"(?:[，。！!、,\s]*(?:有|的|办法|可以|好的|好|是的|对|对的|没问题|了解|知道))*[。！!，,、\s]*$",
    re.I,
)
CUSTOMER_HOLD_REPLY_MARKERS = re.compile(r"没听明白|具体是什么办法|再具体说说|再说清楚|先介绍一下", re.I)


def customer_clarification_reply(scenario: dict[str, Any] | None, history: list[dict[str, Any]]) -> str:
    scenario = scenario or {}
    persona = scenario.get("persona") if isinstance(scenario.get("persona"), dict) else {}
    goal = clean_text(persona.get("goal")) or "我现在这个困扰"
    last_customer = next(
        (clean_text(item.get("content", "")) for item in reversed(history) if item.get("role") == "assistant"),
        "",
    )
    if re.search(r"有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目", last_customer):
        return "我还没听明白，具体是什么办法，适合我这种情况吗？"
    return f"我还没听明白，能再具体说说吗？我主要还是想解决{goal}。"


def employee_message_needs_customer_clarification(history: list[dict[str, Any]], employee_message: str) -> bool:
    employee_message = clean_text(employee_message)
    if not employee_message:
        return True
    if re.search(r"我错了|说错了|不好意思|抱歉|不能做|做不了|没什么不同|没区别|都一样|不适合|多久|多长时间|什么时候开始|哪里|哪个部位|什么位置", employee_message):
        return False
    if CUSTOMER_VAGUE_EMPLOYEE_REPLY.fullmatch(employee_message):
        return True
    if len(employee_message) <= 8 and not re.search(r"[？?]", employee_message):
        return True
    last_customer = next(
        (clean_text(item.get("content", "")) for item in reversed(history) if item.get("role") == "assistant"),
        "",
    )
    asks_for_method = bool(re.search(r"有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目", last_customer))
    if asks_for_method and not re.search(r"方法|办法|方案|项目|体验|流程|步骤|安排|介绍|说明|适合", employee_message):
        return True
    return False


def hidden_objection_index(history: list[dict[str, Any]]) -> int:
    user_turns = sum(1 for item in history if item.get("role") == "user")
    held_turns = sum(
        1 for item in history
        if item.get("role") == "assistant" and CUSTOMER_HOLD_REPLY_MARKERS.search(clean_text(item.get("content", "")))
    )
    return max(0, user_turns - held_turns)


def test_fallback_reply(scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> str:
    scenario = scenario or {}
    persona = scenario.get("persona") if isinstance(scenario.get("persona"), dict) else {}
    goal = clean_text(persona.get("goal")) or "我现在这个困扰"
    employee_message = clean_text(employee_message)
    if re.search(r"我错了|说错了|不好意思|抱歉", employee_message):
        return f"没关系，你重新给我讲清楚就行。我主要还是想解决{goal}。"
    if re.search(r"不能做|做不了|没什么不同|没区别|都一样|不适合", employee_message):
        return f"那我有点没听明白，我主要是{goal}，想知道还有没有别的办法。"
    if re.search(r"多久|多长时间|什么时候开始", employee_message):
        return "有一阵子了，最近感觉比以前明显一些。"
    if re.search(r"哪里|哪个部位|什么位置", employee_message):
        return f"主要就是{goal}，其他地方我暂时没太留意。"
    if employee_message_needs_customer_clarification(history, employee_message):
        return customer_clarification_reply(scenario, history)
    objections = list((scenario or {}).get("hidden_objections") or [])
    turn_number = hidden_objection_index(history)
    if turn_number >= len(objections):
        generic_replies = [
            f"这些专业的我不太懂，我主要就是想解决{goal}。",
            "我现在没有别的问题了，就是还没完全放心。",
            "那我先听到这里，想清楚以后再决定。",
            "我还得再想想，现在不想马上决定。",
            "我听明白一点了，不过心里还是有些犹豫。",
            "我主要担心的还是自己的情况到底能不能改善。",
        ]
        return generic_replies[(turn_number - len(objections)) % len(generic_replies)]
    objection = objections[turn_number]
    templates = {
        "怕疼": "我比较怕疼，过程中会不会很难受？",
        "太贵": "我也有点担心价格会不会太高。",
        "一次有没有用": "我还担心做一次看不到什么变化。",
        "时间": "我平时工作很忙，能安排出来的时间不多。",
        "固定斤数": "我还是很在意到底能不能瘦到自己想要的样子。",
        "价格": "我还要考虑预算，太贵的话可能不会做。",
        "成分/过敏": "我以前皮肤用东西容易不舒服，所以有点担心过敏。",
        "怕设备不安全": "我很怕烫，也担心过程中会不舒服。",
        "医院太贵": "我就是觉得去医院太贵了，所以才想先来问问。",
        "怕手术": "我一想到可能要做手术就很害怕。",
        "怕没效果": "我最怕花了钱却没什么变化。",
        "不信任": "我现在还不太放心，想先听你讲明白。",
        "一次见效": "我还担心做一次是不是看不出变化。",
        "疗效证据": "我以前试过不少方法都没坚持住，怕这次也没用。",
        "不想控制饮食": "如果还要管得特别严格，我可能坚持不了。",
        "回家考虑": "我还不想现在决定，想回去再考虑一下。",
        "药品身份": "我就是不确定这个到底算不算药，心里有点怕。",
        "疾病风险": "我有血糖问题，最担心会不会对身体有影响。",
        "价值不清": "我现在还没听明白贵在哪里。",
        "不愿回答问题": "我不太想说太多私人的事情。",
        "担心隐私": "我最在意的是隐私，不能接受的话我就不做。",
        "担心被强推": "我不希望一来就被一直推着买东西。",
        "担心异常": "我就是担心今天更酸痛是不是不正常。",
        "想继续购买": "如果这次没什么问题，我原本还想继续做。",
        "设备真伪": "我也分不清设备有什么区别，怕花冤枉钱。",
        "服务差异": "我看不出你们和别家到底差在哪里。",
    }
    return templates.get(objection, f"我现在主要还是担心{objection}，其他专业的我也不太懂。")


def customer_reply_is_invalid(reply: str) -> bool:
    if not reply or len(reply) > 100 or TEST_INTERNAL_MARKERS.search(reply) or CUSTOMER_ROLE_DRIFT_MARKERS.search(reply):
        return True
    return reply.count("？") + reply.count("?") > 1


def normalized_customer_reply(reply: str, scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> str:
    reply = clean_text(reply)
    if employee_message_needs_customer_clarification(history, employee_message):
        return customer_clarification_reply(scenario, history)
    previous_customer_replies = [clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"]
    repeated = any(reply == previous or (len(reply) >= 18 and len(previous) >= 18 and reply[:18] == previous[:18]) for previous in previous_customer_replies)
    if scenario and reply == clean_text(scenario.get("opening", "")):
        repeated = True
    if repeated or customer_reply_is_invalid(reply):
        return test_fallback_reply(scenario, history, employee_message)
    return reply


def normalize_training_result(result: dict[str, Any] | None, scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    result["customer_reply"] = normalized_customer_reply(result.get("customer_reply", ""), scenario, history, employee_message)
    feedback = result.get("feedback") if isinstance(result.get("feedback"), dict) else {}
    defaults = {
        "level": "needs_work",
        "issue": f"本轮“{clean_text(employee_message)[:60]}”还需要补充一个更明确的需求或安全问题。",
        "why": "先回答顾客当前问题，再补充一个必要信息，并明确下一步。",
        "method_step": "了解目标并完成问题定位",
        "knowledge_focus": "顾客目标、持续时间、影响和必要安全信息",
        "suggested_reply": "我先确认一个关键信息：这种情况大概持续多久了，对日常生活有什么影响？",
        "next_goal": "下一轮只补充一个必要问题，并承接顾客刚才的回答。",
    }
    normalized_feedback = {}
    for key, fallback in defaults.items():
        value = clean_text(feedback.get(key, ""))
        normalized_feedback[key] = value or fallback
    if normalized_feedback["level"] not in {"good", "needs_work", "critical"}:
        normalized_feedback["level"] = "needs_work"
    if unsafe_claim_hits(employee_message):
        normalized_feedback["level"] = "critical"
    result["feedback"] = normalized_feedback
    return result


def normalize_test_turn_result(result: dict[str, Any] | None, scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    reply = normalized_customer_reply(result.get("reply", ""), scenario, history, employee_message)
    emotion = clean_text(result.get("emotion", "neutral"))
    if emotion not in {"curious", "hesitant", "concerned", "relieved", "neutral"}:
        emotion = "neutral"
    return {"reply": reply, "emotion": emotion, "should_continue": result.get("should_continue") is not False}


def detect_assessment_failures(history: list[dict[str, Any]]) -> list[str]:
    employee_text = " ".join(clean_text(item.get("content", "")) for item in history if item.get("role") == "user")
    customer_text = " ".join(clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant")
    failures = []
    if unsafe_claim_hits(employee_text) or re.search(r"(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)", employee_text, re.I):
        failures.append("CF-02")
    red_flag = re.search(r"胸痛|呼吸困难|晕厥|突发剧痛|进行性麻木无力|发热红肿|腿麻|头晕", customer_text, re.I)
    keeps_selling = re.search(r"可以做|安排项目|先体验|继续做|正常现象|没事", employee_text, re.I)
    safety_stop = re.search(r"暂停|停止|先不|医疗|就医|医院|医生|评估|转介", employee_text, re.I)
    if red_flag and keeps_selling and not safety_stop:
        failures.append("CF-01")
    refused = re.search(r"不想|拒绝|不要触碰|不拍照|回家考虑", customer_text, re.I)
    pressure = re.search(r"必须|今天就|现在就|不买|不做.{0,6}(?:后悔|更严重)", employee_text, re.I)
    if refused and pressure:
        failures.append("CF-03")
    discomfort = re.search(r"疼|灼热|烫|头晕|不舒服|设备异常", customer_text, re.I)
    continues = re.search(r"忍一忍|继续做|正常的|没关系|坚持一下", employee_text, re.I)
    if discomfort and continues and not safety_stop:
        failures.append("CF-04")
    return failures


def fallback_employee_evidence(dimension_id: str, history: list[dict[str, Any]]) -> str:
    employee_messages = [clean_text(item.get("content", "")) for item in history if item.get("role") == "user" and clean_text(item.get("content", ""))]
    patterns = {
        "D1": r"理解|您好|谢谢|可以吗",
        "D2": r"了解|多久|目标|作息|饮食|活动|尝试|影响|担心",
        "D3": r"不能|不承诺|不保证|边界|个体差异|复盘",
        "D4": r"时间|预算|选择|安排|目标|方案",
        "D5": r"理解|担心|顾虑|不能保证|选择|您看",
        "D6": r"安全|健康|暂停|停止|不舒服|医疗|评估",
        "D7": r"下一步|愿意|安排|复盘|确认|跟进",
    }
    pattern = patterns.get(dimension_id, r".")
    selected = next((message for message in reversed(employee_messages) if re.search(pattern, message, re.I)), None)
    if not selected:
        selected = employee_messages[-1] if employee_messages else ""
    return f"员工原话：“{selected[:180]}”" if selected else "对话中未体现"


def evidence_uses_customer_only_text(evidence: str, history: list[dict[str, Any]]) -> bool:
    employee_text = " ".join(clean_text(item.get("content", "")) for item in history if item.get("role") == "user")
    customer_messages = [clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"]
    for message in customer_messages:
        compact = re.sub(r"\s+", "", message)
        for index in range(max(0, len(compact) - 7)):
            fragment = compact[index:index + 8]
            if fragment and fragment in evidence and fragment not in employee_text:
                return True
    return False


def normalize_assessment_result(result: dict[str, Any] | None, history: list[dict[str, Any]]) -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    provided_dimensions = {
        item.get("id"): item
        for item in result.get("dimension_scores", [])
        if isinstance(item, dict) and item.get("id")
    }
    dimensions = []
    for spec in RUBRIC.get("dimensions", []):
        provided = provided_dimensions.get(spec["id"], {})
        try:
            score = round(float(provided.get("score", 0)))
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(spec["weight"], score))
        evidence = clean_text(provided.get("evidence", ""))
        if not evidence or evidence_uses_customer_only_text(evidence, history):
            evidence = fallback_employee_evidence(spec["id"], history)
        dimensions.append({
            "id": spec["id"],
            "name": spec["name"],
            "score": score,
            "max_score": spec["weight"],
            "evidence": evidence,
            "comment": clean_text(provided.get("comment", "")) or "需要在下一轮对话中补充可验证表现。",
        })

    failure_specs = {item["code"]: item for item in RUBRIC.get("critical_failures", [])}
    model_failures = {
        item.get("code"): item
        for item in result.get("critical_failures", [])
        if isinstance(item, dict) and item.get("code") in failure_specs
    }
    for code in detect_assessment_failures(history):
        model_failures.setdefault(code, {"code": code, "evidence": "员工原话触发安全与合规规则。"})
    critical_failures = []
    for code, item in model_failures.items():
        spec = failure_specs[code]
        critical_failures.append({
            "code": code,
            "reason": clean_text(item.get("reason", "")) or spec["rule"],
            "evidence": clean_text(item.get("evidence", "")) or "员工原话触发关键失败项。",
            "score_cap": spec["score_cap"],
        })

    total_score = sum(item["score"] for item in dimensions)
    if critical_failures:
        total_score = min(total_score, min(item["score_cap"] for item in critical_failures))

    def clean_list(value: Any, fallback: list[str]) -> list[str]:
        items = [clean_text(item) for item in value] if isinstance(value, list) else []
        items = [item for item in items if item]
        return items[:4] or fallback

    return {
        "total_score": total_score,
        "dimension_scores": dimensions,
        "critical_failures": critical_failures,
        "strengths": clean_list(result.get("strengths"), ["完成了本轮顾客沟通。"]),
        "improvements": clean_list(result.get("improvements"), ["下一轮请围绕顾客原话补齐需求分析、安全边界和可执行下一步。"]),
        "next_training_scene": clean_text(result.get("next_training_scene", "")) or SCENARIOS[0].get("id"),
        "summary": clean_text(result.get("summary", "")) or "评分已按本轮员工实际表达生成。",
    }


def response_payload(mode: str, result: dict[str, Any], docs: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    citations = public_citations(docs)
    result = sanitize_public_result(result)
    if mode == "qa":
        result["citations"] = citations
    elif isinstance(result, dict):
        result.pop("citations", None)
        citations = []
    return {
        "ok": True,
        "mode": mode,
        "result": result,
        "citations": citations,
        "retrieved": public_retrieved(docs) if mode == "qa" else [],
        "meta": meta,
    }


def apply_methodology_result(result: dict[str, Any], mode: str, route: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    if mode == "qa":
        result["route"] = public_route(route)
        if route.get("intent_id") == "INTENT-PRICE":
            result["answer"] = "价格和活动会随城市、门店、具体项目和日期变化，我不能用历史资料先口头保证。请告诉我您咨询的城市、门店和项目，我会按当前系统里的有效版本核对后准确回复。"
            result["uncertainties"] = ["需要确认城市、门店、具体项目、查询日期和当前生效版本。"]
            result["recommended_action"] = route.get("recommended_next", "确认门店与项目后查询当前系统。")
        elif not result.get("safety_filter_triggered"):
            result["recommended_action"] = route.get("recommended_next", "先确认顾客目标和必要安全信息。")
        elif not clean_text(result.get("recommended_action")):
            result["recommended_action"] = route.get("recommended_next", "先确认顾客目标和必要安全信息。")
        if not isinstance(result.get("uncertainties"), list):
            result["uncertainties"] = []
    elif mode == "training":
        feedback = result.get("feedback") if isinstance(result.get("feedback"), dict) else {}
        feedback.setdefault("method_step", route.get("method_step", "了解目标并完成问题定位"))
        knowledge_focus = "；".join(route.get("knowledge_points", [])[:2]) or route.get("focus", "先确认顾客目标和必要安全信息。")
        feedback.setdefault("knowledge_focus", knowledge_focus)
        result["feedback"] = feedback
    return result


def handle_chat(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "qa")
    action = payload.get("action", "turn")
    message = clean_text(payload.get("message", ""))
    history = payload.get("history") or []
    api_key = payload.get("api_key") or ENV_API_KEY
    model = payload.get("model") or DEFAULT_MODEL
    scenario = scenario_by_id(payload.get("scenario_id")) if mode in {"training", "test"} else None

    if action == "start" and mode in {"training", "test"}:
        return {"ok": True, "mode": mode, "scenario": public_scenario(scenario_by_id(payload.get("scenario_id"))), "message": scenario_by_id(payload.get("scenario_id")).get("opening"), "source_refs": []}
    if not message and action != "finish":
        raise ValueError("请输入内容")

    dialogue_history = clean_dialogue_history(history)
    recent_dialogue = " ".join(item["content"] for item in dialogue_history[-6:])
    query = qa_context_query(message, dialogue_history) if mode == "qa" else clean_text(f"{recent_dialogue} {message}")
    route = route_customer_question(query)
    docs = retrieve(query, limit=8, route=route)
    if mode in {"qa", "training", "test"}:
        docs = with_safety_doc(docs)
    citation_refs = public_citations(docs)

    if mode == "qa":
        user_message = f"顾客当前问题：{message}\n\n方法路由：\n{route_context_block(route)}\n\n检索资料：\n{context_block(docs)}"
        if MOCK_MODE or not api_key:
            result = apply_methodology_result(safety_filter(mock_qa_response(message, route, docs), mode, message, route), mode, route)
            return response_payload(mode, result, docs, {"mock": True, "model": model})
        raw, meta = call_model(QA_SYSTEM, [*dialogue_history, {"role": "user", "content": user_message}], model, api_key, temperature=0.2)
        result = apply_methodology_result(safety_filter(extract_json(raw) or {"answer": raw, "uncertainties": ["模型未按结构化格式返回，请人工核验。"], "citations": citation_refs, "recommended_action": ""}, mode, message, route), mode, route)
        return response_payload(mode, result, docs, {**meta, "mock": False})

    if mode == "training":
        turn_number = sum(1 for item in dialogue_history if item.get("role") == "user") + 1
        training_system = f"{TRAIN_SYSTEM}\n\n顾客可知场景（只供 customer_reply 保持角色一致）：{json.dumps(customer_turn_context(scenario), ensure_ascii=False)}\n当前是第 {turn_number} 轮员工回复。顾客下一句话必须承接员工最新表达，不得重复开场或忽略历史。must_test 及下面的方法、知识只供 feedback 使用，绝不能写进 customer_reply。\n\n方法路由：\n{route_context_block(route)}\n\n相关知识库：\n{context_block(docs, max_docs=4, max_chars_per_doc=650)}"
        if MOCK_MODE or not api_key:
            result = apply_methodology_result(safety_filter(mock_response(mode, action, message, scenario, history, docs), mode, message, route), mode, route)
            result = normalize_training_result(result, scenario, history, message)
            return response_payload(mode, result, docs, {"mock": True, "model": model})
        raw, meta = call_model(training_system, [*dialogue_history, {"role": "user", "content": message}], model, api_key, temperature=0.35, max_tokens=1200)
        result = apply_methodology_result(safety_filter(extract_json(raw) or {"customer_reply": raw, "feedback": {"level": "needs_work", "issue": "模型未按结构化格式返回。", "why": "请检查 Prompt 输出约束。", "suggested_reply": "请继续围绕顾客目标进行追问。", "next_goal": "完成需求分析。"}, "citations": citation_refs}, mode, message, route), mode, route)
        result = normalize_training_result(result, scenario, history, message)
        return response_payload(mode, result, docs, {**meta, "mock": False})

    if mode == "test" and action == "turn":
        hidden_context = json.dumps(customer_turn_context(scenario), ensure_ascii=False)
        turn_number = sum(1 for item in dialogue_history if item.get("role") == "user") + 1
        test_system = f"{TEST_TURN_SYSTEM}\n\n场景设定（只供你使用，不得泄露）：{hidden_context}\n开场白：{scenario.get('opening')}\n当前是员工第 {turn_number} 轮回复。"
        if MOCK_MODE or not api_key:
            result = normalize_test_turn_result(mock_response(mode, action, message, scenario, history, docs), scenario, history, message)
            return response_payload(mode, result, docs, {"mock": True, "model": model})
        raw, meta = call_model(test_system, [*dialogue_history, {"role": "user", "content": message}], model, api_key, temperature=0.55)
        result = normalize_test_turn_result(extract_json(raw) or {"reply": raw}, scenario, history, message)
        return response_payload(mode, result, docs, {**meta, "mock": False})

    if mode == "test" and action == "finish":
        full_dialogue = clean_dialogue_history(history, limit=40)
        dialogue = json.dumps(full_dialogue, ensure_ascii=False)
        rubric_context = json.dumps(RUBRIC, ensure_ascii=False)
        user_message = f"评分表：\n{rubric_context}\n\n本场景方法路由：\n{route_context_block(route)}\n\n场景：\n{json.dumps(scenario, ensure_ascii=False)}\n\n员工完整对话：\n{dialogue}\n\n相关知识库：\n{context_block(docs)}"
        if MOCK_MODE or not api_key:
            result = {
                "total_score": 72,
                "dimension_scores": [{"id": item["id"], "name": item["name"], "score": round(item["weight"] * 0.72), "max_score": item["weight"], "evidence": "本地演示评分，接入真实模型后将引用逐句对话证据。", "comment": "建议继续训练需求分析和异议处理。"} for item in RUBRIC["dimensions"]],
                "critical_failures": [],
                "strengths": ["完成了基本接待并保持了对话连续性。"],
                "improvements": ["先问清目标、持续时间、影响和顾虑，再介绍项目。", "面对价格和效果异议时，使用共情—澄清—回应—确认。"],
                "next_training_scene": SCENARIOS[1].get("id"),
                "summary": "本地演示评分：流程已走通，正式评分需要配置 SiliconFlow API Key。",
            }
            result = normalize_assessment_result(result, full_dialogue)
            return response_payload(mode, result, docs, {"mock": True, "model": model})
        raw, meta = call_model(ASSESS_SYSTEM, [{"role": "user", "content": user_message}], model, api_key, temperature=0.1, max_tokens=3200)
        result = extract_json(raw) or {"total_score": 0, "dimension_scores": [], "critical_failures": [], "strengths": [], "improvements": [raw], "next_training_scene": SCENARIOS[0].get("id"), "summary": "模型未按结构化格式返回，请检查 Prompt。"}
        result = normalize_assessment_result(result, full_dialogue)
        result = sanitize_assessment_advice(result)
        return response_payload(mode, result, docs, {**meta, "mock": False})

    raise ValueError("不支持的模式或操作")


class Handler(BaseHTTPRequestHandler):
    server_version = "KBAI/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, data: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        request_path = self.path.split("?", 1)[0]
        if request_path == "/api/health":
            self.send_json({"ok": True, "api_configured": bool(ENV_API_KEY), "mock_mode": MOCK_MODE, "model": DEFAULT_MODEL, "models": AVAILABLE_MODELS, "knowledge": {"rag_documents": len(RAG_DOCUMENTS), "knowledge_cards": len(CARDS), "objections": len(OBJECTIONS), "scenarios": len(SCENARIOS)}})
            return
        if request_path == "/api/bootstrap":
            self.send_json({"ok": True, "scenarios": [public_scenario(item) for item in SCENARIOS], "models": AVAILABLE_MODELS, "knowledge": {"rag_documents": len(RAG_DOCUMENTS), "knowledge_cards": len(CARDS), "objections": len(OBJECTIONS), "sources": len(SOURCE_REGISTRY)}, "rubric": {"total": RUBRIC.get("total"), "dimensions": [{"id": item["id"], "name": item["name"], "weight": item["weight"]} for item in RUBRIC.get("dimensions", [])]}})
            return
        root_static_files = {"/app.js", "/styles.css", "/showyu-logo.png", "/learning_modules.json", "/learning_catalog.json"}
        if request_path.startswith("/static/") or request_path in root_static_files:
            relative = request_path.removeprefix("/static/").lstrip("/").replace("..", "")
            target = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT.resolve() not in target.parents:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if target.exists() and target.is_file():
                content_type = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png"}.get(target.suffix, "application/octet-stream")
                body = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        if request_path == "/" or request_path == "/index.html":
            target = STATIC_ROOT / "index.html"
            body = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_json(handle_chat(payload))
        except ValueError as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self.send_json({"ok": False, "error": str(exc), "hint": "请检查 API Key、模型名称和网络连接。"}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.send_json({"ok": False, "error": f"服务器处理失败：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)


if __name__ == "__main__":
    print(f"KBAI local server: http://{HOST}:{PORT}")
    print(f"Knowledge base: {len(RAG_DOCUMENTS)} RAG documents / {len(SCENARIOS)} scenarios")
    print(f"SiliconFlow model: {DEFAULT_MODEL} | env key: {'configured' if ENV_API_KEY else 'not configured'} | mock: {MOCK_MODE}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
