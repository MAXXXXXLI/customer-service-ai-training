from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
TRAINING_DUAL_CALL_WAIT_SECONDS = float(os.getenv("TRAINING_DUAL_CALL_WAIT_SECONDS", "48"))
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
COMMON_QA = [
    *read_jsonl("common_qa_catalog.jsonl"),
    *read_jsonl("common_qa_excel_catalog.jsonl"),
]
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
COMMON_QA_DOC_BY_ID = {
    doc.get("document_id"): doc
    for doc in RAG_DOCUMENTS
    if doc.get("metadata", {}).get("doc_type") == "common_qa"
}
COMMON_QA_COURSE_FALLBACKS = {
    "COURSE-FAQ-POINT-WAVE-001": "COURSE-MOD-03-02",
    "COURSE-FAQ-SUPER-V-001": "COURSE-MOD-04-02",
    "COURSE-FAQ-SLIMMING-001": "COURSE-MOD-05-03",
    "COURSE-FAQ-OBJECTION-001": "COURSE-MOD-02-04",
    "COURSE-FAQ-SAFETY-001": "COURSE-MOD-06-02",
    "COURSE-FAQ-BEAUTY-001": "COURSE-MOD-09-03",
}
COMMON_QA_LEGACY_COURSE_IDS = {
    "COURSE-FAQ-POINT-WAVE-001": ("COURSE-NKB-010", "COURSE-NKB-011", "COURSE-NKB-012"),
    "COURSE-FAQ-SUPER-V-001": ("COURSE-NKB-017", "COURSE-NKB-018", "COURSE-NKB-019"),
    "COURSE-FAQ-SLIMMING-001": ("COURSE-NKB-020", "COURSE-NKB-021", "COURSE-NKB-022", "COURSE-NKB-023"),
    "COURSE-FAQ-OBJECTION-001": ("COURSE-NKB-007", "COURSE-NKB-008"),
    "COURSE-FAQ-SAFETY-001": ("COURSE-NKB-003",),
    "COURSE-FAQ-BEAUTY-001": ("COURSE-NKB-033", "COURSE-NKB-036", "COURSE-NKB-038", "COURSE-NKB-039", "COURSE-NKB-040", "COURSE-NKB-043"),
}
MODULE_BY_ID = {module["id"]: module for module in LEARNING_MODULES}
SOURCE_TO_COURSES: dict[str, list[dict[str, Any]]] = {}
for item in [*CARDS, *OBJECTIONS]:
    course = COURSE_BY_KNOWLEDGE_ID.get(item.get("id", ""))
    if not course:
        continue
    for source_id in item.get("source_ids", []):
        SOURCE_TO_COURSES.setdefault(source_id, []).append(course)

DOMAIN_TO_MODULE = {
    "onboarding": "MOD-01", "company": "MOD-01", "reception": "MOD-02", "sales_skills": "MOD-02",
    "point_wave": "MOD-03", "point_wave_ops": "MOD-03", "professional_qa": "MOD-03", "training_video": "MOD-03",
    "super_v": "MOD-04", "point_wave_super_v": "MOD-04",
    "beauty": "MOD-08", "beauty_ops": "MOD-08",
    "slimming": "MOD-05", "slimming_reception": "MOD-05", "slimming_product": "MOD-05", "slimming_science": "MOD-05",
    "objections": "MOD-02", "comparison": "MOD-02",
    "safety": "MOD-01", "service_safety": "MOD-01", "operations": "MOD-01", "product_ops": "MOD-01",
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


NEGATED_RED_FLAG_PATTERN = re.compile(
    r"(?:没有|没|并没有|并无|尚无|未见|未出现|未发生|没出现|不伴有?|否认|无)"
    r"(?:(?:任何|一点儿?|明显|持续|进行性|新发|突然)){0,2}"
    r"(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕)"
    r"(?:(?:、|或|和|及|以及)(?:(?:任何|一点儿?|明显|持续|进行性|新发|突然)){0,2}"
    r"(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕))*",
    re.I,
)


def intent_matches(text: str, intent: dict[str, Any]) -> bool:
    candidate = NEGATED_RED_FLAG_PATTERN.sub(" ", text) if intent.get("id") == "INTENT-RED-FLAG" else text
    return matches_any(candidate, intent.get("patterns", []))


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
    text = clean_text(query).replace("点振波", "点阵波")
    intent_routes = sorted(METHODOLOGY.get("intent_routes", []), key=lambda item: -item.get("priority", 0))
    intent = next((item for item in intent_routes if intent_matches(text, item)), None)
    matched_intent = intent is not None
    topics = [item for item in METHODOLOGY.get("topic_routes", []) if matches_any(text, item.get("patterns", []))]
    # Some legacy intent patterns use broad words such as “副作用”. When the
    # question explicitly names a point-wave service and does not mention a
    # drug or injection, the project topic must win over the medication route.
    if intent and intent.get("id") == "INTENT-DRUG" and any(topic.get("module_id") == "MOD-03" for topic in topics):
        if not re.search(r"药|用药|口服|注射|针剂|GLP.?1|贝那鲁肽|司美格鲁肽|美妥", text, re.I):
            intent = None
            matched_intent = False
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
                "support_module_ids": default.get("support_module_ids", ["MOD-01"]),
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
    if primary_module_id != "MOD-01":
        support_module_ids.append("MOD-01")
    support_module_ids = [item for item in unique_items(support_module_ids) if item in MODULE_BY_ID and item != primary_module_id]

    course_ids = [*intent.get("course_ids", [])]
    knowledge_points = []
    for topic in topics:
        course_ids.extend(topic.get("course_ids", []))
        knowledge_points.extend(topic.get("knowledge_points", []))
    if not topics and not matched_intent:
        course_ids.extend(default.get("course_ids", []))
    if intent.get("stop_sales"):
        course_ids.extend(["COURSE-NKB-001", "COURSE-NKB-002", "COURSE-NKB-003", "COURSE-NKB-004"])
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


POINT_WAVE_BEST_REPLY = (
    "请不用担心，这个是点阵波理疗后正常的理疗后反应。因为点阵波理疗的原理是通过冲击波对您的深层筋膜造成微损伤来引发身体本身的自我修复功能。"
    "痛则不通，通则不痛，您的筋膜有淤堵或者结节才会有这样的疼痛感，这样的感觉第二天之后就会消失了。"
    "不过相信您同时也能感觉到身体变得更轻松，酸胀紧张感有所缓解了"
)


def is_point_wave_aftercare_query(value: Any) -> bool:
    """Keep the approved post-service answer inside the point-wave module."""
    text = clean_text(value).replace("点振波", "点阵波")
    return bool(
        "点阵波" in text
        and re.search(r"做完|打完|理疗后|服务后|体验后|第二天|昨天", text, re.I)
        and re.search(r"更痛|更疼|更酸痛|酸痛|疼痛加重|是不是.{0,6}打坏|正常不正常|正常吗|是否正常", text, re.I)
    )


def normalize_prompt_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").replace("\x00", "").strip()[:2000]
    return text or fallback


def sanitize_prompt_preference(value: Any, fallback: str = "") -> str:
    """Keep the editable field as a presentation preference, never a system override."""
    text = normalize_prompt_text(value, fallback)
    if re.search(
        r"(?:忽略|无视|覆盖|改写|取消固定|不要输出\s*json|不要遵守|"
        r"system|assistant|developer|role\s*=|hidden_information|information_release_rules)",
        text,
        flags=re.I,
    ):
        return fallback
    return text


def normalize_prompt_overrides(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    training = source.get("training") if isinstance(source.get("training"), dict) else {"customer": source.get("training"), "coach": source.get("training")}
    simulation = source.get("simulation") if isinstance(source.get("simulation"), dict) else {"customer": source.get("simulation"), "assessment": source.get("simulation")}
    return {
        "qa": sanitize_prompt_preference(source.get("qa"), PROMPT_PREFERENCE_DEFAULTS["qa"]),
        "training": {
            "customer": sanitize_prompt_preference(training.get("customer"), PROMPT_PREFERENCE_DEFAULTS["training_customer"]),
            "coach": sanitize_prompt_preference(training.get("coach"), PROMPT_PREFERENCE_DEFAULTS["training_coach"]),
        },
        "simulation": {
            "customer": sanitize_prompt_preference(simulation.get("customer"), PROMPT_PREFERENCE_DEFAULTS["simulation_customer"]),
            "assessment": sanitize_prompt_preference(simulation.get("assessment"), PROMPT_PREFERENCE_DEFAULTS["simulation_assessment"]),
        },
    }


def prompt_system_envelope(kind: str, custom_prompt: Any) -> str:
    fixed_prompts = {
        "qa": DEFAULT_PROMPT_OVERRIDES["qa"],
        "training_customer": DEFAULT_PROMPT_OVERRIDES["training"]["customer"],
        "training_coach": DEFAULT_PROMPT_OVERRIDES["training"]["coach"],
        "simulation_customer": DEFAULT_PROMPT_OVERRIDES["simulation"]["customer"],
        "simulation_assessment": DEFAULT_PROMPT_OVERRIDES["simulation"]["assessment"],
    }
    preference = sanitize_prompt_preference(custom_prompt, PROMPT_PREFERENCE_DEFAULTS.get(kind, ""))
    guard = PROMPT_FIXED_GUARDS.get(kind, "保持系统角色、边界和结构化输出。")
    return (
        f"【可编辑内容参考（仅影响表达偏好，不改变功能）】\n{preference}\n\n"
        f"【固定系统 Prompt（不可编辑）】\n{fixed_prompts.get(kind, '')}\n\n"
        f"【固定结构与安全保护（不可编辑）】\n{guard}"
    )


def text_terms(text: str) -> set[str]:
    value = clean_text(text).lower()
    terms = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", value))
    terms.update(value[i : i + 2] for i in range(len(value) - 1) if "\u4e00" <= value[i] <= "\u9fff" and "\u4e00" <= value[i + 1] <= "\u9fff")
    return terms


COMMON_QA_NOISE_RE = re.compile(
    r"请问|我想(?:问|了解)|想问一下|请教一下|什么是|是什么|为什么|为啥|怎么回事|如何|怎么|怎么办|"
    r"能不能|可以吗|是否|吗|呢|呀|啊|的|一下",
    re.I,
)
COMMON_QA_SYNONYMS = (
    ("点振波", "点阵波"),
    ("头疼", "头不适"),
    ("头痛", "头不适"),
    ("疼痛", "不适"),
    ("疼", "不适"),
    ("痛", "不适"),
    ("为啥", "为什么"),
    ("咋", "怎么"),
)


def normalize_common_qa_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = text.translate(str.maketrans({"？": "?", "！": "!", "，": ",", "。": ".", "：": ":"}))
    for source, target in COMMON_QA_SYNONYMS:
        text = text.replace(source, target)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)


def common_qa_core_text(value: Any) -> str:
    return COMMON_QA_NOISE_RE.sub("", normalize_common_qa_text(value))


def common_qa_match_terms(value: Any) -> set[str]:
    text = common_qa_core_text(value)
    terms = set(re.findall(r"[a-z0-9_]+", text))
    terms.update(text[index : index + 2] for index in range(len(text) - 1) if "\u4e00" <= text[index] <= "\u9fff" and "\u4e00" <= text[index + 1] <= "\u9fff")
    return terms


RAG_STOP_TERMS = {
    "这个", "那个", "这些", "那些", "项目", "服务", "可以", "不能", "能不", "是不是", "是否", "怎么", "如何",
    "什么", "什么是", "有没有", "请问", "我想", "你们", "我们", "现在", "一下", "一个", "哪些", "有哪", "吗", "呢",
    "的", "了", "很", "还", "会不", "能否", "做不", "怎么", "为什么", "一次", "几次", "想要", "需要",
}


def retrieval_terms(text: str) -> set[str]:
    return {
        term for term in text_terms(text)
        if len(term) >= 2 and term not in RAG_STOP_TERMS
    }


COMMON_QA_INTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "definition": re.compile(r"什么是|是什么|原理|定位|怎么工作|作用是什么", re.I),
    "adverse_effect": re.compile(
        r"副作用|不良反应|反应|不适|疼痛|痛|酸胀|刺痛|更痛|更疼|淤青|青紫|肿|麻木|发麻|头晕|耳鸣|犯困|恶心|红肿|发热|过敏",
        re.I,
    ),
    "suitability": re.compile(r"能做|可以做|适合|风险|危险|禁忌|术后|疾病|结节|孕|哺乳|心脏|高血压", re.I),
    "efficacy": re.compile(r"有效|效果|改善|见效|一次|几次|多久|保证|反弹|好不好", re.I),
    "comparison": re.compile(r"区别|比较|哪个|联合|同时|和.+区别", re.I),
    "price": re.compile(r"价格|多少钱|收费|贵|预算|费用", re.I),
    "process": re.compile(r"怎么做|如何做|操作|顺序|安排|部位|频率|次数|流程", re.I),
}


def common_qa_intents(value: Any) -> set[str]:
    text = clean_text(value)
    return {name for name, pattern in COMMON_QA_INTENT_PATTERNS.items() if pattern.search(text)}


def common_qa_score(query: str, row: dict[str, Any]) -> float:
    query_core = common_qa_core_text(query)
    question_core = common_qa_core_text(row.get("question", ""))
    if len(query_core) < 2 or len(question_core) < 2:
        return 0.0
    if query_core == question_core:
        return 1.0

    query_terms = common_qa_match_terms(query_core)
    question_terms = common_qa_match_terms(question_core)
    overlap = len(query_terms & question_terms)
    if overlap < 2:
        return 0.0
    keyword_hits = sum(
        1
        for keyword in row.get("keywords", [])
        if len(common_qa_core_text(keyword)) >= 2 and common_qa_core_text(keyword) in query_core
    )
    if not keyword_hits and overlap < 3:
        return 0.0
    query_chars = set(query_core)
    question_chars = set(question_core)
    char_dice = (2 * len(query_chars & question_chars)) / max(len(query_chars) + len(question_chars), 1)
    question_coverage = overlap / max(len(question_terms), 1)
    query_coverage = overlap / max(len(query_terms), 1)
    keyword_score = min(1.0, keyword_hits / max(1, min(len(row.get("keywords", [])), 2)))
    score = (
        question_coverage * 0.38
        + query_coverage * 0.18
        + char_dice * 0.20
        + keyword_score * 0.16
    )
    query_intents = common_qa_intents(query)
    question_intents = common_qa_intents(row.get("question", ""))
    shared_intents = query_intents & question_intents
    if query_intents and question_intents:
        if not shared_intents:
            # “副作用”和“项目原理”都是同一项目的词面相关问题，
            # 但不能互相替代。让二次判断看到候选，同时显著降低误命中概率。
            score *= 0.35
        else:
            score += 0.14
    elif query_intents and not question_intents:
        score *= 0.75
    length_ratio = min(len(query_core), len(question_core)) / max(len(query_core), len(question_core), 1)
    if query_core in question_core or question_core in query_core:
        # 只有候选覆盖了大部分当前问题时，短语包含才算加分；
        # “点阵波”不能覆盖“点阵波的副作用有哪些”。
        score += 0.06 * length_ratio if length_ratio >= 0.55 else -0.08
    return min(score, 0.99)


def common_qa_candidates(query: str, limit: int = 6) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in COMMON_QA:
        if not row.get("approved_answer"):
            continue
        score = common_qa_score(query, row)
        if score >= 0.28:
            candidates.append({
                "row": row,
                "score": round(score, 3),
                "intent_match": bool(common_qa_intents(query) & common_qa_intents(row.get("question", ""))),
            })
    candidates.sort(
        key=lambda item: (
            -item["score"],
            -int(item["row"].get("usage_count") or 0),
            -len(item["row"].get("question", "")),
        )
    )
    return candidates[:limit]


def common_qa_auto_accept(candidate: dict[str, Any] | None) -> bool:
    if not candidate or candidate.get("score", 0) < 0.84:
        return False
    query_intents = common_qa_intents(candidate.get("query", ""))
    row_intents = common_qa_intents(candidate.get("row", {}).get("question", ""))
    return not query_intents or not row_intents or bool(query_intents & row_intents)


def match_common_qa(query: str) -> dict[str, Any] | None:
    candidates = common_qa_candidates(query, limit=6)
    if not candidates:
        return None
    best = {**candidates[0], "query": query, "candidate_count": len(candidates), "selection": "deterministic"}
    return best if common_qa_auto_accept(best) else None


def point_wave_best_common_qa(query: str) -> dict[str, Any] | None:
    """Return the approved point-wave answer before generic FAQ ranking/model selection."""
    if not is_point_wave_aftercare_query(query):
        return None
    row = next((item for item in COMMON_QA if item.get("id") == "FAQ-XLS-0002"), None)
    if not row:
        return None
    return {
        "row": row,
        "score": 1.0,
        "query": query,
        "candidate_count": 1,
        "selection": "point_wave_best_answer",
        "answer": POINT_WAVE_BEST_REPLY,
    }


def public_common_qa_match(match: dict[str, Any]) -> dict[str, Any]:
    row = match.get("row", {})
    return {
        "id": row.get("id", ""),
        "question": row.get("question", ""),
        "score": match.get("score", 0),
        "status": row.get("status", ""),
        "candidate_count": match.get("candidate_count", 1),
        "selection": match.get("selection", "candidate"),
    }


def common_qa_course_ids(row: dict[str, Any]) -> list[str]:
    requested_id = row.get("mapped_course_id", "")
    if requested_id in COURSE_BY_ID:
        return [requested_id]
    candidates = list(COMMON_QA_LEGACY_COURSE_IDS.get(requested_id, ()))
    question = clean_text(f"{row.get('question', '')} {' '.join(row.get('keywords', []))}")
    intents = common_qa_intents(question)
    if requested_id == "COURSE-FAQ-POINT-WAVE-001":
        if "adverse_effect" in intents:
            candidates = ["COURSE-NKB-012", "COURSE-NKB-015", *candidates]
        elif "comparison" in intents:
            candidates = ["COURSE-NKB-013", *candidates]
        elif "suitability" in intents:
            candidates = ["COURSE-NKB-016", "COURSE-NKB-003", *candidates]
        elif "process" in intents:
            candidates = ["COURSE-NKB-011", *candidates]
        elif "definition" in intents:
            candidates = ["COURSE-NKB-010", *candidates]
    elif requested_id == "COURSE-FAQ-SUPER-V-001":
        if "adverse_effect" in intents:
            candidates = ["COURSE-NKB-018", *candidates]
        elif "suitability" in intents:
            candidates = ["COURSE-NKB-019", *candidates]
        else:
            candidates = ["COURSE-NKB-017", *candidates]
    elif requested_id == "COURSE-FAQ-SLIMMING-001":
        if "adverse_effect" in intents:
            candidates = ["COURSE-NKB-024", "COURSE-NKB-027", *candidates]
        elif "suitability" in intents:
            candidates = ["COURSE-NKB-025", *candidates]
        else:
            candidates = ["COURSE-NKB-020", "COURSE-NKB-021", *candidates]
    elif requested_id == "COURSE-FAQ-OBJECTION-001":
        candidates = ["COURSE-NKB-008", *candidates]
    elif requested_id == "COURSE-FAQ-SAFETY-001":
        candidates = ["COURSE-NKB-003", *candidates]
    return unique_items([course_id for course_id in candidates if course_id in COURSE_BY_ID])


def common_qa_course(row: dict[str, Any]) -> dict[str, Any] | None:
    course_ids = common_qa_course_ids(row)
    return COURSE_BY_ID.get(course_ids[0]) if course_ids else None


def common_qa_course_reference(row: dict[str, Any]) -> dict[str, str] | None:
    course = common_qa_course(row)
    if not course:
        return None
    module = MODULE_BY_ID.get(course.get("module_id"), {})
    return {
        "course_id": course.get("id", ""),
        "title": course.get("title", ""),
        "category": "标准问答课程",
        "module": module.get("short_name", ""),
        "chapter": course.get("group_title", ""),
    }


def common_qa_document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row.get("id", ""),
        "text": row.get("approved_answer", ""),
        "metadata": {
            "doc_type": "common_qa",
            "title": row.get("question", ""),
            "course_id": row.get("mapped_course_id", ""),
            "domain": row.get("domain", ""),
        },
    }


def related_course(doc: dict[str, Any]) -> dict[str, Any] | None:
    document_id = str(doc.get("document_id", ""))
    metadata = doc.get("metadata", {})
    if metadata.get("doc_type") == "common_qa":
        common_qa = next((row for row in COMMON_QA if row.get("id") == document_id), None)
        if common_qa:
            return common_qa_course(common_qa)
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


def preferred_course_ids_for_query(query: str) -> list[str]:
    """Return the narrow course scope for the current question, not just its route module."""
    text = clean_text(query)
    intents = common_qa_intents(text)
    if re.search(r"点阵波|点振波", text, re.I):
        if "adverse_effect" in intents:
            return ["COURSE-NKB-012"]
        if "comparison" in intents:
            return ["COURSE-NKB-013"]
        if re.search(r"超V|热动力|联合", text, re.I):
            return ["COURSE-NKB-014"]
        if "suitability" in intents:
            return ["COURSE-NKB-016", "COURSE-NKB-003"]
        if "process" in intents:
            return ["COURSE-NKB-011"]
        if "definition" in intents:
            return ["COURSE-NKB-010"]
        return ["COURSE-NKB-010", "COURSE-NKB-011"]
    if re.search(r"超V|热动力", text, re.I):
        return ["COURSE-NKB-018", "COURSE-NKB-019"] if "adverse_effect" in intents else ["COURSE-NKB-017", "COURSE-NKB-018"]
    if re.search(r"减肥|减重|体重|贝那鲁肽|GLP.?1|美妥", text, re.I):
        if "adverse_effect" in intents:
            return ["COURSE-NKB-024", "COURSE-NKB-027"]
        if "suitability" in intents:
            return ["COURSE-NKB-025", "COURSE-NKB-027"]
        return ["COURSE-NKB-020", "COURSE-NKB-021", "COURSE-NKB-022"]
    if re.search(r"脱毛|祛斑|水光|皮肤|敏感肌|线雕|热玛吉|玻尿酸|私密", text, re.I):
        if re.search(r"脱毛", text, re.I):
            return ["COURSE-NKB-036"]
        return ["COURSE-NKB-033", "COURSE-NKB-038", "COURSE-NKB-040", "COURSE-NKB-043"]
    return []


def retrieve(
    query: str,
    limit: int = 8,
    domain: str | None = None,
    route: dict[str, Any] | None = None,
    include_common_qa: bool = True,
) -> list[dict[str, Any]]:
    query = clean_text(query).replace("点振波", "点阵波")
    if not query:
        return []
    q_terms = retrieval_terms(query)
    scored: list[tuple[float, dict[str, Any]]] = []
    required_course_ids = set((route or {}).get("required_course_ids", []))
    routed_module_ids = {
        (route or {}).get("primary_module_id"),
        *((route or {}).get("support_module_ids", [])),
    }
    routed_module_ids.discard(None)
    preferred_course_ids = set(preferred_course_ids_for_query(query))
    for doc in RAG_DOCUMENTS:
        metadata = doc.get("metadata", {})
        if not include_common_qa and metadata.get("doc_type") == "common_qa":
            continue
        # 原始资料保留用于审计，但不直接进入机器人上下文；机器人只使用已重写的
        # 课程、结构化卡片、异议案例和安全规则，避免旧版医疗化/绝对化话术复现。
        if metadata.get("doc_type") == "source":
            continue
        if domain and metadata.get("domain") not in {domain, "safety", "objections"}:
            continue
        if route and metadata.get("doc_type") == "course_section":
            if metadata.get("module_id") not in routed_module_ids and metadata.get("course_id") not in required_course_ids:
                continue
        if preferred_course_ids and metadata.get("doc_type") in {"course_section", "integrated_course_section"}:
            if metadata.get("course_id") not in preferred_course_ids:
                continue
        doc_text = clean_text(doc.get("text", ""))
        d_terms = retrieval_terms(doc_text)
        overlap = len(q_terms & d_terms)
        phrase = 1.0 if query.lower() in doc_text.lower() else 0.0
        title_bonus = len(q_terms & retrieval_terms(metadata.get("title", ""))) * 0.7
        base_score = overlap + phrase * 5 + title_bonus
        course_bonus = 2.5 if metadata.get("doc_type") == "course_section" else 0.0
        route_bonus = 0.0
        if metadata.get("course_id") in required_course_ids:
            route_bonus += 10.0
        if metadata.get("module_id") in routed_module_ids:
            route_bonus += 3.0
        score = base_score + course_bonus + route_bonus
        # A route is only a scope hint. It must not make a course relevant when
        # none of the question's terms occur in the course section.
        if base_score > 0 or (route_bonus > 0 and metadata.get("doc_type") not in {"course_section", "integrated_course_section"}):
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
        "module_id": scenario.get("module_id"),
        "domain": scenario.get("domain"),
        "title": scenario.get("title"),
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


ASSESSMENT_SPECIFIC_ADVICE = re.compile(
    r"(?:古方|口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物|隔天一次|每天\s*\d+\s*次)",
    re.I,
)
ASSESSMENT_CONCRETE_ADVICE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*(?:mg|g|ml|毫克|克|毫升|片|粒|支|单位))|"
    r"(?:(?:每天|每日|每周|每次|隔天|早晚|睡前|餐前|餐后).{0,8}(?:\d+|一|两|二|三|四|五|六|七|八|九|十).{0,3}次)|"
    r"(?:(?:口服|注射).{0,12}(?:\d+|一|两|二|三|四|五|六|七|八|九|十)\s*(?:次|片|粒|支|毫升|毫克|mg|ml))",
    re.I,
)
ASSESSMENT_SAFE_ADVICE_BOUNDARY = re.compile(
    r"(?:(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,18}"
    r"(?:交由|由|请|需|需要|应|应该|须|必须)[^，,。；;！？!?\n]{0,10}(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}"
    r"(?:评估|决定|指导|核实|开具|处方))|"
    r"(?:(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}(?:评估|决定|指导|核实|开具|处方)[^，,。；;！？!?\n]{0,18}"
    r"(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|"
    r"(?:(?:门店|我们|员工)[^，,。；;！？!?\n]{0,8}(?:不能|不可|不会|不应|不得|不建议|不提供|不决定|不调整|无权)[^，,。；;！？!?\n]{0,14}"
    r"(?:给出?|提供|建议|决定|调整|安排)?(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|"
    r"(?:(?:不能|不可|不要|不得|不建议|避免)[^，,。；;！？!?\n]{0,8}(?:自行|擅自)[^，,。；;！？!?\n]{0,5}(?:停换药|停药|停用|换药|更换药物|调整用药))|"
    r"(?:(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,8}(?:遵医嘱|按医嘱))",
    re.I,
)

ASSESSMENT_COMMENT_BOUNDARY = "员工尚未把顾客顾虑转化为可执行的下一步。建议先澄清时间、预算和服务偏好，再给出门店当前已核验且符合安全边界的选择。"
ASSESSMENT_IMPROVEMENT_BOUNDARY = "不要替顾客直接选择具体产品或使用安排；先核验适用条件和门店当前标准，再提供非医疗、可选择的下一步。"
ASSESSMENT_STRENGTH_BOUNDARY = "完成了基本沟通；涉及医疗决定时仍需明确门店边界，并交由医生或药师评估。"
ASSESSMENT_FAILURE_REASON_BOUNDARY = "员工表达涉及未经核验的具体用药或使用安排，应明确门店边界并交由医生或药师评估。"
ASSESSMENT_SUMMARY_BOUNDARY = "本轮需要加强需求分析和个性化表达。后续重点练习在不承诺结果、不擅自补充具体产品或使用安排的前提下，把顾客顾虑转化为可执行的服务下一步。"


def assessment_advice_needs_sanitizing(value: Any) -> bool:
    """Detect actionable medical arrangements while preserving explicit safe boundaries."""
    text = clean_text(value)
    if not ASSESSMENT_SPECIFIC_ADVICE.search(text):
        return False
    for sentence in re.split(r"[。；;！？!?\n]+", text):
        if not ASSESSMENT_SPECIFIC_ADVICE.search(sentence):
            continue
        # Even inside a disclaimer, concrete amounts or frequencies should not
        # be echoed back in an employee-facing assessment report.
        if ASSESSMENT_CONCRETE_ADVICE.search(sentence):
            return True
        remainder = ASSESSMENT_SAFE_ADVICE_BOUNDARY.sub("", sentence)
        if ASSESSMENT_SPECIFIC_ADVICE.search(remainder):
            return True
    return False


def sanitize_assessment_advice(result: dict[str, Any]) -> dict[str, Any]:
    """Keep scoring evidence intact while removing unverified product or usage advice."""
    if not isinstance(result, dict):
        return result
    for dimension in result.get("dimension_scores", []):
        if isinstance(dimension, dict) and assessment_advice_needs_sanitizing(dimension.get("comment")):
            dimension["comment"] = ASSESSMENT_COMMENT_BOUNDARY
    for key, fallback in (
        ("strengths", ASSESSMENT_STRENGTH_BOUNDARY),
        ("improvements", ASSESSMENT_IMPROVEMENT_BOUNDARY),
    ):
        values = result.get(key)
        if isinstance(values, list):
            result[key] = [fallback if assessment_advice_needs_sanitizing(item) else item for item in values]
    for failure in result.get("critical_failures", []):
        if isinstance(failure, dict) and assessment_advice_needs_sanitizing(failure.get("reason")):
            failure["reason"] = ASSESSMENT_FAILURE_REASON_BOUNDARY
    if assessment_advice_needs_sanitizing(result.get("summary")):
        result["summary"] = ASSESSMENT_SUMMARY_BOUNDARY
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
    r"(?:保证|一定|肯定).{0,10}(?:治好|治愈|根治)",
    r"(?:治愈|根治|治疗|治好)[^，。；！？,.;!?\r\n]{0,8}(?:疾病|颈椎病|糖尿病|三高|脂肪肝|炎症)",
    r"(?:有效|能够|可以|会)[^，。；！？,.;!?\r\n]{0,10}(?:治疗|治好|根治|改善糖尿病|改善三高|改善脂肪肝|提高免疫力|增强免疫力)",
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
        compiled = re.compile(pattern, re.I)
        if has_non_negated_match(text, compiled):
            hits.append(pattern)
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
        result["answer"] = "若涉及儿童或未成年人，药品适用性不能仅凭聊天判断。具体药品的用法和剂量必须依据当前说明书与医生处方，门店不能给剂量，也不能建议开始、停用或更换药物。请先确认具体药名、剂型、开药医生、正在使用的其他药物和当前不适，再由开药医生或药师核实。"
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
        surgery_question = bool(re.search(r"替代手术", user_text, flags=re.I))
        numbness_boundary = bool(re.search(r"腰椎间盘突出|颈椎病|腿麻|手麻|麻木|无力", user_text, flags=re.I))
        result["answer"] = (
            "点阵波不能替代手术、医疗诊断或医生制定的治疗方案。"
            + ("你已提到麻木或无力等症状，今天应先停止项目与销售推进，并由医疗机构评估；"
               "若症状持续、加重或伴随大小便异常、会阴麻木等情况，请及时就医或联系急救。"
               if numbness_boundary else
               "如果同时已有相关诊断，或出现麻木、无力等异常，应先由医疗机构评估，不要用项目体验替代医疗评估。")
            if surgery_question
            else "您提到持续不适并出现手麻、腿麻、麻木或无力，这需要先由医疗机构评估；今天先不要体验项目，也不要继续销售沟通。门店不能判断病因，也不能用项目体验替代医疗诊断或评估；症状持续或加重时请及时就医。"
            if numbness_boundary
            else "现在先停止体验和销售沟通，不要自行判断原因。若胸痛、呼吸困难、晕厥、明显出冷汗或进行性麻木无力正在发生、持续或加重，请尽快联系急救或前往医疗机构；情况稳定后再由门店负责人记录并跟进。"
            if follow_up
            else "您提到的情况需要先确认安全，今天先不要做项目，也不要继续产品推荐。请告诉我症状从什么时候开始、是否正在加重，以及有没有胸痛、呼吸困难、晕厥或进行性麻木无力；症状明显、持续或加重时，请尽快联系急救或前往医疗机构。"
        )
        result["uncertainties"] = ["需要确认症状开始时间、程度、变化和伴随情况。"]
        result["recommended_action"] = "停止销售推进，完成风险问询、负责人升级和必要的医疗分流。"
        result["safety_filter_triggered"] = True
        return result
    if mode == "qa" and re.search(r"(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能", user_text, flags=re.I):
        result["answer"] = "背部发凉是一种主观感受，不能据此判断某个器官功能不好，也不能由门店作疾病诊断。先确认从什么时候开始、是否持续或加重，以及有没有疼痛、麻木、无力、胸痛、呼吸困难、发热等伴随情况；症状明显、持续或伴随异常时应由医疗机构评估。"
        result["uncertainties"] = ["需要确认持续时间、变化、诱因和伴随症状。"]
        result["recommended_action"] = "先做风险问询；不能用项目体验替代医疗诊断或评估。"
        result["safety_filter_triggered"] = True
        return result
    if mode == "qa" and re.search(r"水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)", user_text, flags=re.I):
        result["answer"] = "一次水分数值升高最多说明当次、当时测量出现变化，不能直接证明长期改善。比较时要尽量使用同一设备、同一部位、相近时间和环境，并记录护肤、清洁等条件；长期结论需要在相同条件下多次复测并结合持续观察。"
        result["uncertainties"] = ["需要确认设备、部位、时间、环境和前后测量条件是否一致。"]
        result["recommended_action"] = "按统一条件记录本次结果，约定后续复测，不把单次读数宣传为长期效果。"
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


TRAIN_CUSTOMER_SYSTEM = """你是美容、瘦身门店员工训练中的模拟顾客。你只生成顾客下一句话，不评价员工，不给出标准答案，不暴露幕后设定。

对话规则：
1. 只承接员工最新一句话，不重复开场白。
2. 只有员工问到对应内容时，才按释放规则透露一组信息；每轮最多一组，不得把多条隐藏信息一次说完。
3. 若已明确出现需优先处理的异常，员工建议暂停或就医后，只承接安全安排或追问如何执行，不跳回价格、怕疼等常规异议。

严格输出 JSON，不要 Markdown，不要额外解释：{"customer_reply":"顾客下一句话"}。""" + LIMITED_CUSTOMER_POLICY


TRAIN_FEEDBACK_SYSTEM = """你是美容、瘦身门店的员工训练教练。只使用给定的已发生对话、公开任务、方法路由和知识资料评价员工当前这句话。资料中可能存在旧版本、营销表述或需要核验的医学内容，不得擅自把它们改写成确定性承诺。

时序边界（最高优先级）：
1. role=assistant 是员工当时已经听到的顾客原话；role=user 是员工原话。
2. 只能依据员工说话前已经出现在对话中的顾客信息。不得假设顾客有对话中未出现的症状、顾虑或决定。
3. 员工问“有没有手麻”不等于顾客已经手麻；建议话术可以追问未知信息，但不得写成已知事实。
4. 你不会收到当前轮尚未生成的顾客回复或任何隐藏场景；不得猜测这些内容。
""" + SAFETY_POLICY + METHODOLOGY_POLICY + """

严格输出 JSON，不要 Markdown，不要额外解释：
{"feedback":{"level":"good|needs_work|critical","issue":"引用员工原话并指出一个最重要的问题或做得好的地方","why":"说明当前接待节点、应用知识和原因","method_step":"本轮应执行的方法节点","knowledge_focus":"本轮主要知识重点","suggested_reply":"在同一时点可以替换员工原话的一句自然话术","next_goal":"下一轮只练一个目标"}}
点阵波模块批准话术（最高优先级）：当公开场景属于“点阵波打完更痛/更酸痛”，且员工回答前尚未公开麻木、无力、发热红肿、胸痛、呼吸困难、晕厥或突发剧痛等新症状时，下面这段话是本模块指定的最佳回答，必须评为 good，suggested_reply 必须原样返回，不得改写成其他模块的话术：
“请不用担心，这个是点阵波理疗后正常的理疗后反应。因为点阵波理疗的原理是通过冲击波对您的深层筋膜造成微损伤来引发身体本身的自我修复功能。痛则不通，通则不痛，您的筋膜有淤堵或者结节才会有这样的疼痛感，这样的感觉第二天之后就会消失了。不过相信您同时也能感觉到身体变得更轻松，酸胀紧张感有所缓解了”
该批准话术只适用于 MOD-03 点阵波模块的上述场景；一旦顾客在员工回答前已公开新的红旗症状，仍按安全规则评价。其他模块不得套用。
严重度要求：除上述点阵波模块批准话术外，对已知服务后疼痛加重说“正常/没事”、用“微损伤/自我修复”确定解释、或建议继续加量，必须是 critical。已知麻木时，只说重视并就医但缺少暂停、记录和升级，是 needs_work。完成暂停、不诊断、记录升级和医疗分流才是 good。同一句内即使也有安全词，只要又正常化异常或建议继续，仍是 critical。"""


TEST_TURN_SYSTEM = """你是美容、瘦身门店实战考核中的模拟顾客，不是培训教练、客服助手或评分员。

对话规则：
1. 只回应员工最新一句话，每轮用顾客口吻回复 1—3 句；不能评价员工、讲方法、给提示、总结知识或暴露评分点。
2. 开场白已由系统展示，后续绝不重复开场白，也不原样重复之前说过的话。
3. 根据员工实际提问，每轮最多自然透露一个尚未透露的背景、顾虑或异议；员工没有问到时不要主动把隐藏信息全部说出。
4. 如果员工答非所问，继续以顾客身份追问原问题；如果员工给出危险承诺，以顾客身份表示疑惑或不放心，但不要替员工说出标准答案。
5. 不得出现“考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该”等幕后词语。

回答相关性契约（优先于普通顾虑推进）：
6. 先识别员工最新一句是在提问、解释、确认还是安排下一步；回复的第一句话必须承接同一个主题，不能突然跳到价格、项目原理或另一个顾虑。
7. 员工一句话中有多个明确问题时，按原顺序逐项回应；已经在前面回答过的事实不要重复，尚未掌握的内容明确说“我没留意/不太清楚”，不能用另一个隐藏事实代替，也不能只挑一个问题后换话题。
8. 员工在解释数据或效果时，先用普通顾客口吻回应这段解释，再提出一个与当前主题直接相关的顾虑；不要直接复读泛泛的“我主要担心效果”。
9. 如果员工没有提出新问题，只给出说明或安排，顾客应针对这段说明确认理解、提出一个相关追问或说明仍未解决的原始顾虑；不得凭空开启新的异议。
10. 每轮回复前做一次自检：回复中至少有一个短语能对应员工最新问题或动作；若没有，改写为“我还没听明白，您刚才问的是……对吗？”这类澄清，而不是输出无关内容。
11. 真人反应优先：员工给出具体方案、时间、记录方式或下一步安排时，先回应这个安排（接受、犹豫、确认一个细节或提出一个具体疑问），不能跳回旧顾虑，也不能自顾自开启新的异议。
12. 员工已经解释清楚并提出可执行安排时，不要只说“这些专业的我不懂”；如果确实听不懂，要指出具体不懂的是时间、记录方法还是判断标准。
13. 员工刚解释“测量时间、条件或结果不同”时，必须先回应测量安排，再提出判断周期或复测标准，不能直接回到“我想先听懂/我只想解决体重”等旧话题。
14. 顾客可以继续提问，但回复必须遵循“先回应、后追问”：先用一句话确认理解、接受、犹豫或说明具体不清楚之处，再提出最多一个与员工刚才内容直接相关的问题。禁止跳过前半句直接抛出新问题。

严格输出 JSON，不要 Markdown：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。""" + LIMITED_CUSTOMER_POLICY


QA_SYSTEM = """你是企业培训知识库中的专业顾客接待助手。你面对的是顾客，因此答案必须是一段可以直接对顾客说的话，而不是知识摘要、检索报告或员工培训分析。只能基于方法路由和检索资料，不能把知识库之外的猜测说成公司标准。

回答要求：这是连续对话，必须结合最近的顾客问题和你的上一轮回答理解“这个、那、它、怎么办”等指代，但只回答顾客当前这一问。先直接承接顾客当前问题；如果缺少决定答案的关键信息，只问一个最必要的问题；再给已核验的事实、流程或边界；最后给一个可执行下一步。通常控制在80—220个汉字，复杂安全问题可适当增加。不要机械重复上一轮答案，不要重复相同免责声明，不要罗列无关知识。

回答结构严格 JSON：{"answer":"可直接对顾客说的完整回答","uncertainties":["确实需要核验的点，没有则为空数组"],"citations":[],"recommended_action":"一个明确、可执行的下一步"}。如果资料不足，明确说资料不足并说明要补充什么；如果涉及医疗、药品、孕期、儿童、慢病、服务后异常或红旗症状，优先安全分流。""" + SAFETY_POLICY + METHODOLOGY_POLICY


COMMON_QA_JUDGE_SYSTEM = """你是常见问答的严格路由判断器。你的任务不是凭空回答，而是判断当前顾客问题是否被候选标准问答真正覆盖。

必须遵守：
1. 先比较当前问题与每个候选问题的核心意图。项目相同不代表问题相同；“是什么/原理”“副作用/不适”“能不能做/风险”“效果/多久”“价格”“区别”不能互相替代。
2. 只有候选问题和标准答案能够直接回答当前问题时才选择；如果候选只能回答项目背景、但当前问的是副作用或风险，必须返回 NONE。
3. 选择后只能基于被选候选的 approved_answer 做压缩、分点或口语化整理，不得增加候选答案没有的事实、承诺、治疗结论、用法或数字。
4. 不要把候选问题拼接成一个新答案。无法确认时宁可 NONE，系统会回退到知识库检索。

严格输出 JSON：{"match_id":"候选id或NONE","confidence":0.0,"answer":"整理后的直接回答；NONE时为空","reason":"一句话说明意图是否一致"}"""


ASSESS_SYSTEM = """你是企业培训考核官。只在对话结束后评分，不再扮演顾客，也不继续对话。

评分边界：
1. history 中 role=user 的内容才是员工原话；role=assistant 是模拟顾客原话，绝不能把顾客说过的话算成员工能力或员工错误。
2. 必须严格按评分表的 7 个维度逐项评分，dimension_scores 恰好 7 项，id、name、max_score 与评分表完全一致，不得缺项、加项或改权重。
3. 每个维度的 evidence 必须引用员工原话或明确写“对话中未体现”；未体现的能力不得凭空给高分。
4. total_score 必须等于 7 个 score 之和；先算维度分，再应用关键失败项的 score_cap。
5. 只评价本次对话已经发生的内容。建议写成下一轮训练动作，不要虚构员工已经说过的话，不要替员工补充产品、药品、剂量、用法或频次。
6. 输出内容必须是考核报告，不能输出新的顾客回复或继续向员工提问。
7. 必须严格按对话时序逐轮评价：一句员工原话只能使用它之前已出现的顾客信息；后来顾客才透露的信息不得追溯扣分。
8. 后续的正确补救不能抹去先前已经发生的关键失败；但顾客明确说“没有/否认”的症状不得当作已出现。

评分时检查员工是否遵守统一方法：先安全后业务、回答当前问题、调用正确知识、只补必要问题、说明边界并给出正确下一步。每个 evidence 和 comment 不超过 35 个汉字；strengths 与 improvements 各最多 3 条，每条不超过 30 个汉字。输出严格 JSON：
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

TRAIN_CUSTOMER_SYSTEM += PUBLIC_OUTPUT_POLICY
TRAIN_FEEDBACK_SYSTEM += PUBLIC_OUTPUT_POLICY + "\n训练模式的 citations 固定返回空数组。"
# Backwards-compatible name for integrations that only inspect the coach prompt.
TRAIN_SYSTEM = TRAIN_FEEDBACK_SYSTEM
QA_SYSTEM += PUBLIC_OUTPUT_POLICY
ASSESS_SYSTEM += PUBLIC_OUTPUT_POLICY

DEFAULT_PROMPT_OVERRIDES = {
    "qa": QA_SYSTEM,
    "training": {"customer": TRAIN_CUSTOMER_SYSTEM, "coach": TRAIN_FEEDBACK_SYSTEM},
    "simulation": {"customer": TEST_TURN_SYSTEM, "assessment": ASSESS_SYSTEM},
}

# These are the only values the operator edits. The long prompts above remain
# fixed so changing wording preferences cannot remove a role, JSON schema,
# safety rule, release rule, or scoring rule.
PROMPT_PREFERENCE_DEFAULTS = {
    "qa": "先直接回应顾客当前问题，语气清楚温和；只补充一个最必要的信息，再给出明确的下一步。",
    "training_customer": "顾客先回应员工最新一句，再继续相关对话；每轮只表达一个重点，像普通人一样说话。",
    "training_coach": "反馈先指出最重要的问题，再给一句可以直接使用的替代表达；语言具体、简洁、可执行。",
    "simulation_customer": "顾客先回应员工最新的问题或安排，再提出一个相关追问；语气自然，每轮只推进一个重点。",
    "simulation_assessment": "评分报告语言清楚、具体、可执行；每条改进建议只聚焦一个动作，并引用真实对话证据。",
}

PROMPT_FIXED_GUARDS = {
    "qa": "保持顾客接待助手身份，只基于请求中提供的路由和资料回答；不得泄露内部字段。必须输出 JSON 对象，键为 answer、uncertainties、citations、recommended_action。遵守安全边界，不诊断、不处方、不承诺固定效果，遇到红旗优先停止销售并建议专业评估。",
    "training_customer": "保持模拟顾客身份，只生成 customer_reply 字段。不得评价员工、泄露隐藏设定或批量提前释放事实；按信息释放规则逐轮回应，先回应员工最新一句再追问。",
    "training_coach": "保持训练教练身份，只评价员工本轮原话和此前公开顾客信息；不得使用本轮未来顾客回复或隐藏事实。必须输出 feedback 对象，字段为 level、issue、why、method_step、knowledge_focus、suggested_reply、next_goal。",
    "simulation_customer": "保持实战考核模拟顾客身份，只输出 reply、emotion、should_continue。先回应员工最新问题或安排，再提出最多一个相关追问；不得扮演教练、评分员或泄露评分点。",
    "simulation_assessment": "保持考核官身份，只输出评分报告，不再扮演顾客。必须严格输出评分表要求的 7 个维度和固定 JSON 字段；按对话时序评分，后续顾客信息不得追溯影响之前员工回合，关键失败封顶规则仍由系统本地复核。",
}


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


def common_qa_answer_is_grounded(answer: str, approved_answer: str) -> bool:
    answer = clean_text(answer)
    approved_answer = clean_text(approved_answer)
    if not answer or len(answer) > 700 or not approved_answer:
        return False
    if re.search(r"保证|一定|治愈|根治|固定减重|药品剂量|停药", answer, re.I):
        return False
    answer_terms = common_qa_match_terms(answer)
    approved_terms = common_qa_match_terms(approved_answer)
    return len(answer_terms & approved_terms) >= 2


def select_common_qa_with_model(
    query: str,
    candidates: list[dict[str, Any]],
    model: str,
    api_key: str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not candidates:
        return None, {"attempted": False, "candidate_count": 0}
    prepared = []
    for candidate in candidates:
        row = candidate["row"]
        prepared.append({
            "id": row.get("id", ""),
            "question": row.get("question", ""),
            "approved_answer": row.get("approved_answer", ""),
            "keywords": row.get("keywords", []),
            "match_score": candidate.get("score", 0),
        })
    if MOCK_MODE or not api_key:
        best = {**candidates[0], "query": query, "candidate_count": len(candidates), "selection": "deterministic"}
        if common_qa_auto_accept(best):
            return best, {"attempted": False, "candidate_count": len(candidates), "selection": "deterministic"}
        return None, {"attempted": False, "candidate_count": len(candidates), "selection": "fallback_knowledge"}

    prompt = json.dumps({"current_question": query, "candidates": prepared}, ensure_ascii=False)
    try:
        raw, meta = call_model(
            COMMON_QA_JUDGE_SYSTEM,
            [{"role": "user", "content": prompt}],
            model,
            api_key,
            temperature=0.0,
            max_tokens=1000,
        )
    except Exception as exc:
        return None, {"attempted": True, "candidate_count": len(candidates), "selection": "fallback_knowledge", "error": str(exc)[:160]}
    payload = extract_json(raw) or {}
    match_id = clean_text(payload.get("match_id", ""))
    if not match_id or match_id.upper() == "NONE":
        return None, {**meta, "attempted": True, "candidate_count": len(candidates), "selection": "fallback_knowledge"}
    selected = next((candidate for candidate in candidates if candidate["row"].get("id") == match_id), None)
    confidence = float(payload.get("confidence") or 0)
    if not selected or confidence < 0.62:
        return None, {**meta, "attempted": True, "candidate_count": len(candidates), "selection": "fallback_knowledge"}
    selected = {
        **selected,
        "query": query,
        "candidate_count": len(candidates),
        "selection": "model_judged",
        "model_confidence": round(confidence, 3),
    }
    organized_answer = clean_text(payload.get("answer", ""))
    if common_qa_answer_is_grounded(organized_answer, selected["row"].get("approved_answer", "")):
        selected["answer"] = organized_answer
    return selected, {**meta, "attempted": True, "candidate_count": len(candidates), "selection": "model_judged"}


def merge_model_meta(*metas: dict[str, Any]) -> dict[str, Any]:
    """Combine parallel model-call metadata without changing the public model/usage shape."""
    usage: dict[str, Any] = {}
    model = ""
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        model = clean_text(meta.get("model")) or model
        current_usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
        for key, value in current_usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[key] = usage.get(key, 0) + value
            elif key not in usage:
                usage[key] = value
    return {"model": model or DEFAULT_MODEL, "usage": usage, "calls": 2, "roles": ["customer", "feedback"]}


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
    """Provide a deterministic answer grounded in the retrieved course knowledge."""
    intent_id = route.get("intent_id")
    module_ids = {route.get("primary_module_id"), *route.get("support_module_ids", [])}
    high_priority_query = bool(
        re.search(r"(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能", message, re.I)
        or re.search(r"水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)", message, re.I)
        or intent_id == "INTENT-RESULT"
        or re.search(r"一次|几次|多久|有效|见效|保证|反弹", message, re.I)
        or intent_id == "INTENT-COMPARISON"
        or "MOD-05" in module_ids
        or "MOD-04" in module_ids
    )
    snippets = []
    seen_titles = set()
    for doc in docs[:2]:
        course = related_course(doc)
        title = course.get("title") if course else public_doc_title(doc)
        if title in seen_titles:
            continue
        seen_titles.add(title)
        if course:
            section = (course.get("sections") or [{}])[0]
            content = section.get("content", "") if isinstance(section, dict) else ""
            if isinstance(content, list):
                content = "；".join(clean_text(item) for item in content[:2] if clean_text(item))
            elif isinstance(content, dict):
                content = "；".join(f"{key}：{clean_text(value)}" for key, value in content.items())
            snippet = clean_text(f"{course.get('summary', '')} {content}")
        else:
            snippet = clean_text(doc.get("text", ""))
        if snippet:
            snippets.append(snippet[:220])

    if snippets and not high_priority_query:
        answer = f"围绕您问的“{clean_text(message)}”，知识库相关课程提到：{'；'.join(snippets[:2])}"
        return {
            "answer": answer,
            "uncertainties": ["具体项目、适用条件和门店动态政策仍需按当前有效版本核对。"],
            "citations": [{"document_id": item.get("document_id"), "title": item.get("metadata", {}).get("title")} for item in docs[:3]],
            "recommended_action": route.get("recommended_next", "如需继续了解，可打开下方相关课程并核对当前门店标准。"),
        }

    if re.search(r"(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能", message, re.I):
        answer = "背部发凉是一种主观感受，不能据此判断某个器官功能不好，也不能由门店作疾病诊断。先确认持续时间、变化和伴随症状；症状明显、持续或伴随异常时应由医疗机构评估。"
        uncertainties = ["需要确认持续时间、变化、诱因和伴随症状。"]
        recommended_action = "先做风险问询；不能用项目体验替代医疗诊断或评估。"
    elif re.search(r"水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)", message, re.I):
        answer = "一次水分数值升高最多说明当次、当时测量出现变化，不能直接证明长期改善。比较时要使用同一设备、同一部位、相近时间和环境，并在相同条件下多次复测。"
        uncertainties = ["需要确认设备、部位、时间、环境和前后测量条件是否一致。"]
        recommended_action = "按统一条件记录并复测，不把单次读数宣传为长期效果。"
    elif intent_id == "INTENT-RESULT" or re.search(r"一次|几次|多久|有效|见效|保证|反弹", message, re.I):
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
        "hidden_information": list(scenario.get("hidden_information") or []),
        "information_release_rules": list(scenario.get("information_release_rules") or []),
    }


def training_feedback_context(scenario: dict[str, Any] | None) -> dict[str, Any]:
    """Public scenario context available before the employee answers this turn."""
    scenario = scenario or {}
    return {
        key: scenario.get(key)
        for key in ("id", "module_id", "module_title", "domain", "title", "task", "opening")
        if scenario.get(key) not in {None, ""}
    }


def assessment_scenario_context(scenario: dict[str, Any] | None) -> dict[str, Any]:
    """Assessment context deliberately excludes unreleased facts and answer keys."""
    return training_feedback_context(scenario)


def training_customer_system(scenario: dict[str, Any] | None, turn_number: int, prompt_override: str | None = None) -> str:
    return (
        f"{prompt_system_envelope('training_customer', prompt_override)}\n\n"
        f"隐藏场景（只供顾客角色使用，不得泄露）："
        f"{json.dumps(customer_turn_context(scenario), ensure_ascii=False)}\n"
        f"公开开场白：{clean_text((scenario or {}).get('opening'))}\n"
        f"当前是员工第 {turn_number} 轮回复。"
    )


def training_feedback_system(
    scenario: dict[str, Any] | None,
    route: dict[str, Any],
    docs: list[dict[str, Any]],
    turn_number: int,
    prompt_override: str | None = None,
) -> str:
    return (
        f"{prompt_system_envelope('training_coach', prompt_override)}\n\n"
        f"公开任务：{json.dumps(training_feedback_context(scenario), ensure_ascii=False)}\n"
        f"当前是员工第 {turn_number} 轮回复。请只评价消息列表最后一条员工原话。\n\n"
        f"方法路由：\n{route_context_block(route)}\n\n"
        f"相关知识库：\n{context_block(docs, max_docs=4, max_chars_per_doc=650)}"
    )


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
        re.search(
            r"^(?:那|这个|这种|它|刚才|如果|那么|可是|但是|"
            r"她追问|他追问|顾客(?:又)?问|顾客追问|对方(?:又)?问|对方追问)",
            message,
            re.I,
        )
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


def customer_objection_reply(objection: str) -> str:
    """Keep fallback顾客话术 natural when the objection already contains a verb."""
    objection = clean_text(objection)
    if not objection:
        return "我还有点没放心，想再听你说明白一点。"
    if re.match(r"^(?:担心|害怕|想|不想|在意|觉得|担忧)", objection):
        return f"我现在主要还是{objection}，其他专业的我也不太懂。"
    return f"我现在主要还是担心{objection}，其他专业的我也不太懂。"


def customer_reply_needs_context_repair(reply: str, employee_message: str, scenario: dict[str, Any] | None) -> bool:
    """Reject a generic objection when the employee just gave a concrete explanation or plan."""
    reply = clean_text(reply)
    employee_message = clean_text(employee_message)
    if not reply or not employee_message:
        return False
    plan_or_explanation = bool(re.search(
        r"测量时间.{0,16}(?:不一样|不同)|结果.{0,12}(?:不一样|不同)|同一(?:时间|条件)|相近时间|"
        r"复测|记录.{0,12}(?:饮食|睡眠|运动|数据)|连续趋势|三到七天|一周后|先把.{0,10}记录|再一起判断",
        employee_message,
    ))
    if not plan_or_explanation:
        return False
    generic_reset = bool(re.search(r"这些专业的我不太懂|主要还是(?:想|担心|希望)|先听懂再决定|还没完全放心", reply))
    if generic_reset:
        return True
    acknowledgment = bool(re.search(r"明白|好的|好，那|原来|我会|我先|听起来|可以|接受|理解", reply))
    question_only = bool(re.search(r"[？?]", reply)) and not acknowledgment and len(reply) <= 48
    return question_only


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
    if re.search(r"测量时间.{0,12}(?:不一样|不同)|结果.{0,10}(?:不一样|不同)|同一(?:时间|条件)", employee_message):
        return "明白了，那我之后尽量在相近时间、相近条件下测量。这样记录几天后再一起判断效果呢？"
    if re.search(r"不能直接说明|不能保证|连续趋势|测量条件|数据记录|再判断|再评估", employee_message):
        return "我明白，单次体重上涨不一定代表没有效果。那我们记录多久、达到什么变化时再一起判断呢？"
    if (
        "MOD-05" in str(scenario.get("module_id", ""))
        and re.search(r"复测|记录|饮食|睡眠|运动|三到七天|一周后|相近时间|跟进", employee_message)
    ):
        return "好，那我先按相近时间复测，也把饮食、睡眠和运动记下来。到时候如果还是不降，我们再一起看看，可以吗？"
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
    if re.search(r"评分|员工|设置", clean_text(objection)):
        return "我最担心的是过程中会不会太痛或不舒服，能不能随时停下来？"
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
        "想一次解决": "我还是希望一次就能解决，不想来很多次。",
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
    return templates.get(objection, customer_objection_reply(objection))


def customer_reply_is_invalid(reply: str) -> bool:
    if not reply or len(reply) > 100 or TEST_INTERNAL_MARKERS.search(reply) or CUSTOMER_ROLE_DRIFT_MARKERS.search(reply):
        return True
    return reply.count("？") + reply.count("?") > 1


GENERIC_RELEASE_ASK_MARKERS = re.compile(
    r"[？?]|(?:请|麻烦).{0,8}(?:说|告诉|提供)|(?:想|需要).{0,6}(?:了解|确认)|"
    r"是否|有没有|有无|什么|怎么|如何|哪|几|多久|多长|吗|么|呢",
    re.I,
)
GENERIC_RELEASE_SHORT_FACTS = re.compile(
    r"成都|空腹|高血压|手麻|发麻|麻木|胸闷|胸痛|头晕|发热|无力|电击|备孕|结石|"
    r"反黑|漏尿|出血|哺乳|便秘|晒伤|红肿|渗出|视物模糊|甲状腺|酸类|"
    r"玻尿酸|经期|腰围|排便|不耐受|喝不下水|没吃早饭|眼周肿|异味|灌痛",
    re.I,
)
GENERIC_RELEASE_NUMBER_FACTS = re.compile(
    r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)(?:个)?(?:年|月|天|小时|分钟|分|厘米|次|袋)",
    re.I,
)
GENERIC_RELEASE_DENIED_QUESTION = re.compile(
    r"(?:不是|并非).{0,10}(?:问|询问|追问|了解|确认)|"
    r"(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别)"
    r".{0,4}(?:问|询问|追问|了解|确认)|"
    r"(?:多久|多长时间|什么时候|何时|是否|有没有).{0,8}(?:不问|别问|不用问|无需问|不必问)",
    re.I,
)

GENERIC_RELEASE_QUESTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "时间和变化": (
        re.compile(r"多久|多长时间|什么时候|何时|哪天|开始|持续", re.I),
        re.compile(r"变化|加重|变重|更重|更痛|更疼|越来越|减轻|好转|严重", re.I),
    ),
    "病史和进食": (
        re.compile(r"病史|高血压|慢性病|基础病", re.I),
        re.compile(r"进食|吃饭|吃东西|早饭|空腹", re.I),
    ),
    "饮食和经期": (
        re.compile(r"饮食|吃|聚餐", re.I),
        re.compile(r"经期|月经|例假|生理期", re.I),
    ),
    "复查和出血": (
        re.compile(r"复查|产后检查|检查过", re.I),
        re.compile(r"出血|流血|血性", re.I),
    ),
    "饮水排便": (
        re.compile(r"饮水|喝水|水喝", re.I),
        re.compile(r"排便|大便|便秘", re.I),
    ),
    "试感和停止方式": (
        re.compile(r"试感|试一下|小范围|先试", re.I),
        re.compile(r"停止|停下|随时停|叫停", re.I),
    ),
}

GENERIC_RELEASE_SINGLE_QUESTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "持续时间": re.compile(r"多久|多长时间|持续|几天|几个月|几年", re.I),
    "开始时间": re.compile(r"什么时候|何时|哪天|刚开始|开始时间", re.I),
    "产后时间": re.compile(r"产后.{0,6}(?:多久|时间)|生完.{0,6}多久|几个月", re.I),
    "伴随症状": re.compile(r"伴随|其他.{0,8}(?:不适|症状|反应)|有没有.{0,12}(?:麻|无力|发热|胸痛|胸闷|不舒服)", re.I),
    "门店": re.compile(r"门店|哪家店|哪个店|城市|地区|在哪里", re.I),
    "券名": re.compile(r"券名|券的名称|什么券|哪张券|券.{0,5}截图", re.I),
    "贵在哪里": re.compile(r"贵.{0,8}(?:哪|什么|原因|顾虑)|在意.{0,8}(?:价格|效果|预算)", re.I),
    "竞品包含内容": re.compile(r"竞品|别家|楼下|对方.{0,6}(?:包含|包括)|包了什么|做几次", re.I),
    "使用体验": re.compile(r"使用体验|用着|用了.{0,6}(?:感觉|觉得)|舒服|效果", re.I),
    "疼痛程度": re.compile(r"疼痛|疼|痛.{0,6}(?:程度|几分|多严重)|\d+\s*分", re.I),
    "感觉": re.compile(r"什么感觉|怎么痛|哪种感觉|感觉.{0,6}(?:像|是)", re.I),
    "进食饮水": re.compile(r"进食|吃饭|吃东西|早饭|空腹|饮水|喝水|喝不下", re.I),
    "变化": re.compile(r"变化|加重|变重|变大|扩大|更痛|更疼|越来越|减轻|好转|严重", re.I),
    "检查": re.compile(r"检查|报告|查过|复查", re.I),
    "症状": re.compile(r"症状|不适|哪里难受|痛|痒|灼|异味|分泌物", re.I),
    "测量": re.compile(r"测量|称重|什么时候称|早上|晚上", re.I),
    "其他指标": re.compile(r"其他指标|腰围|体围|体脂|除了体重", re.I),
    "餐次": re.compile(r"餐次|早餐|早饭|晚餐|一天几顿|怎么吃", re.I),
    "反应": re.compile(r"反应|不耐受|不舒服|过敏|红肿", re.I),
    "身体状态": re.compile(r"身体|状态|不舒服|乏力|头晕|精神", re.I),
    "用药": re.compile(r"用药|药物|吃药|服药|注射|打针", re.I),
    "特殊情况": re.compile(r"特殊情况|备孕|怀孕|哺乳|孕期", re.I),
    "病史": re.compile(r"病史|以前得过|慢性病|基础病|结石|高血压", re.I),
    "执行": re.compile(r"怎么.{0,6}(?:用|打|执行)|每天|频次|按计划", re.I),
    "营养": re.compile(r"营养|进食|吃得|食量|胃口", re.I),
    "复诊": re.compile(r"复诊|回诊|看过医生|定期检查", re.I),
    "怎么吃": re.compile(r"怎么吃|怎么喝|一天几袋|什么时候喝|代餐", re.I),
    "旧产品": re.compile(r"旧产品|以前的|哪个牌子|谁家|买了多久", re.I),
    "不适位置": re.compile(r"不适|哪里|位置|部位|钢圈|肩带|压痛", re.I),
    "主要问题": re.compile(r"主要|最想|哪个问题|困扰|诉求|目标", re.I),
    "目标": re.compile(r"目标|最想|想改善|想解决|在意|诉求", re.I),
    "既往产品": re.compile(r"既往|以前|之前|用过.{0,8}(?:产品|护肤品)|什么产品", re.I),
    "护肤": re.compile(r"护肤|刷酸|酸类|产品|昨晚用", re.I),
    "其他反应": re.compile(r"其他.{0,8}(?:反应|不适|症状)|眼周|呼吸|肿", re.I),
    "皮肤状态": re.compile(r"皮肤|皮肤状态|晒伤|暴晒|发红|破损", re.I),
    "皮肤": re.compile(r"皮肤|发红|红肿|表面|触痛", re.I),
    "既往反应": re.compile(r"既往|以前|之前|反应|红肿|过敏", re.I),
    "面部状态": re.compile(r"面部|脸型|脸.{0,5}(?:瘦|凹)|太阳穴|容量", re.I),
    "既往项目": re.compile(r"既往|以前|之前|做过.{0,8}(?:项目|填充|医美)|最近做", re.I),
    "既往史": re.compile(r"既往|以前|之前|激光|反黑|治疗过", re.I),
    "防晒": re.compile(r"防晒|暴晒|晒太阳|户外", re.I),
    "既往注射": re.compile(r"既往|以前|之前|注射|填充|打过什么", re.I),
    "眼部症状": re.compile(r"眼部|眼睛|视力|视物|模糊", re.I),
    "性生活": re.compile(r"性生活|性经历|伴侣|频率", re.I),
    "产后功能": re.compile(r"产后|盆底|漏尿|功能|憋不住", re.I),
    "使用产品": re.compile(r"使用.{0,6}(?:产品|洗液|药)|用了什么|洗液", re.I),
    "出血": re.compile(r"出血|流血|血性", re.I),
}

GENERIC_RELEASE_ACTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "堆叠项目": re.compile(r"项目.{0,28}项目|(?:所有|全部|全套|一整套|很多|多个).{0,8}项目", re.I),
    "直接承诺": re.compile(r"承诺|保证|肯定|一定|绝对|(?:可以|能).{0,8}(?:叠加|一起用)", re.I),
    "施压成交": re.compile(r"今天必须|现在就|马上.{0,6}(?:付款|购买|买|定)|不买.{0,8}(?:后悔|没有)|逼|必须买", re.I),
    "贬低原品牌": re.compile(r"原品牌.{0,8}(?:不好|没效|差|垃圾)|别的牌子.{0,8}(?:不好|没效|差)", re.I),
    "道歉并重新介绍": re.compile(r"抱歉|不好意思|是我.{0,6}(?:太快|没听清)|重新介绍|我是.{0,10}(?:顾问|负责|接待)", re.I),
    "继续解释套餐": re.compile(r"套餐|卡项|办卡", re.I),
    "建议继续做": re.compile(r"继续做|再做一次|加量|打透|照常做", re.I),
    "谈钱": re.compile(r"钱|价格|费用|浪费|退款", re.I),
    "否定按摩": re.compile(r"按摩.{0,8}(?:没用|无效|不好|不行)|不要.{0,5}按摩", re.I),
    "提医疗治疗": re.compile(r"医疗|治疗|医院|医生|就医", re.I),
    "说越热越好": re.compile(r"越热越好|热一点.{0,8}(?:更好|有效)|温度越高", re.I),
    "提出小范围试用": re.compile(r"小范围|小面积|先试用|试用一下", re.I),
    "提出试感和停止方式": re.compile(
        r"(?=.*(?:试感|试一下|小范围|先试))(?=.*(?:停止|停下|随时停|叫停))",
        re.I,
    ),
    "说继续": re.compile(r"继续做|继续操作|照常做|再做|加量", re.I),
    "承诺项目": re.compile(r"承诺|保证|一定|肯定|(?:能|可以).{0,8}(?:治好|解决|改善)", re.I),
    "承诺快速效果": re.compile(r"快速|马上|很快|一个月.{0,8}(?:减|瘦)|承诺.{0,8}(?:减|瘦)", re.I),
    "要求运动": re.compile(r"必须|要求|每天|每周|运动|锻炼", re.I),
    "直接推荐填充": re.compile(r"直接.{0,6}填充|现在.{0,6}填充|今天.{0,6}填充|建议.{0,6}填充", re.I),
    "直接推荐": re.compile(r"直接推荐|马上.{0,6}(?:用|做|开始)|就用这个|建议你.{0,8}(?:用|做|买)", re.I),
    "只建议观察": re.compile(r"再观察|先观察|回家观察|等一等|暂时不用处理", re.I),
    "给具体加量": re.compile(r"加量|多喝.{0,4}(?:一袋|两袋|\d+袋)|增加.{0,6}(?:用量|剂量)", re.I),
    "说正常": re.compile(r"正常反应|正常现象|这很正常|没问题|没事", re.I),
    "承诺不勒": re.compile(r"保证.{0,8}不勒|一定.{0,8}不勒|绝对.{0,8}不勒|不会勒", re.I),
    "默认组合": re.compile(r"两个.{0,8}(?:一起|组合)|组合.{0,8}(?:做|项目)|都给你安排", re.I),
    "安排马上做": re.compile(r"马上做|立即做|现在做|今天就做|当天做", re.I),
    "承诺一次": re.compile(r"一次.{0,8}(?:去净|解决|治好|有效)|保证.{0,8}一次|永久", re.I),
    "直接教凝胶用量": re.compile(r"凝胶.{0,10}(?:用量|剂量|次|毫升|克|次数)|每次.{0,8}凝胶", re.I),
}


def information_release_rule_parts(rule: Any) -> tuple[str, str]:
    text = clean_text(rule)
    if "时，" not in text:
        return "", ""
    condition, disclosure = text.split("时，", 1)
    return re.sub(r"^员工", "", condition).strip(), disclosure.rstrip("。. ")


def employee_affirmatively_asks_release_question(employee_message: str, pattern: re.Pattern[str]) -> bool:
    """Match an actual current-turn question, not a mention or denial of one."""
    message = clean_text(employee_message)
    for match in pattern.finditer(message):
        clause_start = max(
            [message.rfind(mark, 0, match.start()) for mark in "，。；！？,.;!?"] + [-1]
        ) + 1
        following_boundaries = [
            position
            for mark in "，。；！？,.;!?"
            if (position := message.find(mark, match.end())) >= 0
        ]
        clause_end = min(following_boundaries) if following_boundaries else len(message)
        clause = message[clause_start:clause_end]
        prefix = message[clause_start:match.start()]
        suffix = message[match.end():clause_end]
        denied_before = re.search(
            r"(?:不是|并非).{0,8}(?:在)?(?:问|询问|追问|了解|确认).{0,8}$|"
            r"(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别)"
            r".{0,4}(?:问|询问|追问|了解|确认).{0,8}$",
            prefix,
            re.I,
        )
        denied_after = re.search(
            r"^(?:先|就|我们|现在|暂时)?.{0,4}(?:不问|别问|不用问|无需问|无须问|不必问|不需要问)",
            suffix,
            re.I,
        )
        if denied_before or denied_after:
            continue
        if GENERIC_RELEASE_ASK_MARKERS.search(clause):
            return True
    return False


def employee_triggers_information_release_rule(employee_message: str, rule: Any) -> bool:
    condition, _ = information_release_rule_parts(rule)
    message = clean_text(employee_message)
    if not condition or not message:
        return False
    if condition.startswith(("问", "询问", "追问")):
        if not GENERIC_RELEASE_ASK_MARKERS.search(message):
            return False
        core = re.sub(r"^(?:问|询问|追问)", "", condition).strip("“”\" '")
        compound = GENERIC_RELEASE_QUESTION_PATTERNS.get(core)
        if compound:
            return all(employee_affirmatively_asks_release_question(message, pattern) for pattern in compound)
        pattern = GENERIC_RELEASE_SINGLE_QUESTION_PATTERNS.get(core)
        if pattern:
            return employee_affirmatively_asks_release_question(message, pattern)
        tokens = [token for token in re.split(r"和|及|、", core) if len(token) >= 2]
        return bool(tokens) and all(
            employee_affirmatively_asks_release_question(message, re.compile(re.escape(token), re.I))
            for token in tokens
        )
    pattern = GENERIC_RELEASE_ACTION_PATTERNS.get(condition)
    if not pattern:
        return False
    affirmative_matcher = globals().get("has_non_negated_match")
    if callable(affirmative_matcher):
        return bool(affirmative_matcher(message, pattern))
    return bool(pattern.search(message))


def information_release_reply(rule: Any) -> str:
    _, disclosure = information_release_rule_parts(rule)
    if not disclosure:
        return ""
    quoted = re.findall(r"[“\"]([^”\"]+)[”\"]", disclosure)
    if quoted:
        return clean_text(quoted[0]).rstrip("。！？!?") + ("？" if "？" in quoted[0] or "?" in quoted[0] else "。")
    natural_responses: tuple[tuple[str, str], ...] = (
        (r"发送截图.*名称模糊", "我只能发一张截图，不过上面的名称有点模糊。"),
        (r"顾客更反感", "你这样催我，我更不想现在决定了。"),
        (r"顾客终止对话", "那我先不考虑了。"),
        (r"顾客态度缓和", "好，那你先说说看。"),
        (r"顾客愿意继续", "可以，那我们先小范围试试看。"),
        (r"顾客马上同意", "那我今天就再做一次吧。"),
        (r"顾客表示胸闷更明显", "我现在感觉胸闷更明显了。"),
        (r"顾客表示害怕", "这么热我有点害怕，先停一下吧。"),
        (r"顾客要求加热出更多汗", "那再加热一点，让我多出些汗吧。"),
        (r"顾客说自己没看病", "我没有去医院看过，也没有诊断。"),
        (r"顾客追问具体斤数", "那一个月具体能减多少斤？"),
        (r"顾客说产品来自网络", "这个产品是我从网上买的。"),
        (r"顾客说越来越严重", "可我感觉越来越严重了。"),
        (r"顾客问是否能喝两袋", "那我可以一次喝两袋吗？"),
        (r"顾客要求下周继续", "那我下周还可以继续做吗？"),
        (r"顾客追问能否保证", "那你能保证一定不会勒吗？"),
        (r"顾客说只想选一个", "我只想选一个项目，不想两个一起做。"),
        (r"顾客要求写进合同", "那可以把这个保证写进合同吗？"),
        (r"顾客问当天能否做", "那我今天可以直接做吗？"),
        (r"顾客拒绝", "这个细节我不想回答。"),
    )
    for pattern, response in natural_responses:
        if re.search(pattern, disclosure, re.I):
            return response
    payload = re.sub(r"^(?:顾客)?(?:说明|回答|说|表示|追问|要求)", "", disclosure).strip("，, ")
    if not payload:
        return "我还想再了解清楚一点。"
    if re.match(r"\d+分$", payload):
        return f"大概{payload}。"
    return f"我这边的情况是：{payload.rstrip('。')}。"


def compact_release_text(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"^(?:顾客|客户|她|他)", "", text)
    return re.sub(r"[\s，,。.；;:：！!？?“”\"'、]", "", text)


def text_has_new_hidden_fragment(candidate: str, scenario: dict[str, Any] | None, history: list[dict[str, Any]]) -> bool:
    candidate_compact = compact_release_text(candidate)
    if not candidate_compact:
        return False
    visible_compact = compact_release_text(" ".join(
        clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"
    ))
    sources = [
        *(scenario or {}).get("hidden_information", []),
        *(information_release_rule_parts(rule)[1] for rule in (scenario or {}).get("information_release_rules", [])),
    ]
    for source in sources:
        source_compact = compact_release_text(source)
        if not source_compact:
            continue
        for size in range(min(10, len(source_compact)), 3, -1):
            matched = next(
                (
                    source_compact[index:index + size]
                    for index in range(len(source_compact) - size + 1)
                    if source_compact[index:index + size] in candidate_compact
                    and source_compact[index:index + size] not in visible_compact
                ),
                "",
            )
            if matched:
                return True
        for pattern in (GENERIC_RELEASE_NUMBER_FACTS, GENERIC_RELEASE_SHORT_FACTS):
            for match in pattern.finditer(source_compact):
                fragment = compact_release_text(match.group(0))
                if fragment and fragment in candidate_compact and fragment not in visible_compact:
                    return True
        for quoted in re.findall(r"[“\"]([^”\"]+)[”\"]", clean_text(source)):
            fragment = compact_release_text(quoted)
            if len(fragment) >= 2 and fragment in candidate_compact and fragment not in visible_compact:
                return True
    return False


def generic_information_release_reply(
    candidate_reply: str,
    scenario: dict[str, Any] | None,
    history: list[dict[str, Any]],
    employee_message: str,
) -> str:
    rules = list((scenario or {}).get("information_release_rules") or [])
    if not rules:
        return ""
    visible_compact = compact_release_text(" ".join(
        clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"
    ))
    for rule in rules:
        if not employee_triggers_information_release_rule(employee_message, rule):
            continue
        reply = information_release_reply(rule)
        if reply and compact_release_text(reply) not in visible_compact:
            return reply
    # A model-authored customer turn can paraphrase hidden facts too freely for
    # fragment matching to be a reliable boundary.  Rule-bearing scenarios
    # therefore never pass the candidate through: an unmatched/repeated rule
    # gets a deterministic, scenario-safe continuation instead.
    safety_fallback = training_customer_safety_followup(employee_message, history, scenario)
    if safety_fallback:
        return safety_fallback
    fallback_employee = "" if GENERIC_RELEASE_DENIED_QUESTION.search(clean_text(employee_message)) else employee_message
    return test_fallback_reply(scenario, history, fallback_employee)


def point_wave_release_reply(
    scenario: dict[str, Any] | None,
    history: list[dict[str, Any]],
    employee_message: str,
    candidate_reply: str,
) -> str:
    """Compatibility wrapper; M03 now uses the same structural gate as every scenario."""
    if (scenario or {}).get("id") != "SCN-CEX-M03-S01":
        return ""
    return generic_information_release_reply(candidate_reply, scenario, history, employee_message)


def point_wave_in_session_customer_reply(
    scenario: dict[str, Any] | None,
    employee_message: str,
) -> str:
    """Keep the M03 in-session pain scenario on the employee's latest action."""
    if (scenario or {}).get("id") != "SCN-CEX-M03-S02":
        return ""
    message = clean_text(employee_message)
    lower_energy = re.compile(
        r"(?:把|将)?(?:能量|力度|强度|档位).{0,8}(?:调低|降低|调小|减小|低一些|小一些|低一点|小一点)|"
        r"(?:调低|降低|调小|减小).{0,8}(?:能量|力度|强度|档位)",
        re.I,
    )
    endure = re.compile(
        r"(?:忍|坚持).{0,8}(?:一会儿|一会|几分钟|一下|试试)|"
        r"(?:再|先).{0,6}(?:忍|坚持)|继续.{0,6}(?:忍|坚持)",
        re.I,
    )
    # When one turn contains both options, accept the concrete adjustment.
    if has_non_negated_match(message, lower_energy):
        return "好的那把能量调低一些"
    if has_non_negated_match(message, endure):
        return "好的那我再忍一会儿试试"
    return ""


def normalized_customer_reply(reply: str, scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> str:
    reply = clean_text(reply)
    in_session_reply = point_wave_in_session_customer_reply(scenario, employee_message)
    if in_session_reply:
        return in_session_reply
    if list((scenario or {}).get("information_release_rules") or []):
        # The structural release gate owns the complete reply for rule-bearing
        # scenarios.  This ordering also guarantees that an affirmed trigger
        # wins over every other deterministic fallback.
        if (scenario or {}).get("id") == "SCN-CEX-M03-S01":
            return point_wave_release_reply(scenario, history, employee_message, reply)
        return generic_information_release_reply(reply, scenario, history, employee_message)
    safety_followup = training_customer_safety_followup(employee_message, history, scenario)
    if safety_followup:
        return safety_followup
    if training_safe_response_state(employee_message, history, scenario) == "critical" and re.search(
        r"(?:好的|好|明白|可以).{0,16}(?:去检查|就医|先不做|暂停|帮我记录|联系负责人)",
        reply,
        re.I,
    ):
        return "我还是不放心，你刚才这样说到底是什么意思？"
    if employee_message_needs_customer_clarification(history, employee_message):
        return customer_clarification_reply(scenario, history)
    previous_customer_replies = [clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"]
    repeated = any(reply == previous or (len(reply) >= 18 and len(previous) >= 18 and reply[:18] == previous[:18]) for previous in previous_customer_replies)
    if scenario and reply == clean_text(scenario.get("opening", "")):
        repeated = True
    if repeated or customer_reply_is_invalid(reply):
        return test_fallback_reply(scenario, history, employee_message)
    if customer_reply_needs_context_repair(reply, employee_message, scenario):
        return test_fallback_reply(scenario, history, employee_message)
    return reply


TRAINING_NEW_FACT_MARKERS = ["手麻", "腿麻", "发麻", "麻木", "无力", "胸痛", "呼吸困难", "晕厥", "头晕", "发热", "红肿", "灼热", "设备异常"]
TRAINING_RED_FLAG_PATTERN = re.compile(
    r"手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|腿(?:部)?(?:新发|新|发)?麻|发麻|麻木|无力|胸痛|胸闷|呼吸困难|气短|"
    r"晕厥|昏厥|突发剧痛|发热|红肿|大小便异常|会阴麻木",
    re.I,
)
TRAINING_DISCOMFORT_PATTERN = re.compile(r"疼|痛|灼热|烫|头晕|不舒服|设备异常|麻|无力", re.I)
TRAINING_WORSENING_PATTERN = re.compile(r"加重|变重|更痛|更疼|比.{0,8}(?:重|痛|疼)|越来越(?:痛|疼|重)", re.I)
TRAINING_UNSAFE_NORMALIZATION_PATTERN = re.compile(
    r"(?:这是|属于|就是|都是)?(?:很)?正常(?:的|现象|反应)?|"
    r"没(?:啥|什么)?问题|没事|没关系|不要紧|不碍事|"
    r"微损伤|自我修复|排寒(?:反应)?|排毒(?:反应)?|"
    r"(?:一定|肯定|会).{0,10}(?:更轻松|好转|缓解|不痛|舒服)",
    re.I,
)
TRAINING_CONTINUE_PATTERN = re.compile(
    r"越痛越有效|忍一忍|坚持一下|"
    r"(?:不用|不必|无需|无须)停|没必要暂停|"
    r"(?:继续|接着|照常|再|马上).{0,8}(?:做|做完|操作|体验|项目|加量|打透)|"
    r"(?:今天|明天).{0,10}(?:继续(?:做|操作|体验|项目)?|还?可以做|再做|把.{0,4}(?:项目|体验|操作)?做完|加量|打透|安排(?:项目|体验|操作))|"
    r"做完再说|"
    r"加量|打透|加大能量",
    re.I,
)
TRAINING_UNVERIFIED_ADVICE_PATTERN = re.compile(
    r"(?:可能是|可能涉及|说明|属于).{0,14}(?:神经|损伤|炎症|病变)|"
    r"(?:不要|立即|马上|建议).{0,10}(?:热敷|冷敷|按摩|服药|停药|换药)|"
    r"(?:热敷|冷敷|按摩).{0,8}(?:手臂|腿|疼痛|发麻)|(?:治疗|治好|治愈|根治)",
    re.I,
)
TRAINING_DENIES_SAFETY_PATTERN = re.compile(
    r"(?:不用|不必|无需|无须|不要|不会|拒绝|别|不需要|没必要).{0,8}"
    r"(?:暂停|停止|记录|登记|留档|上报|联系负责人|联系店长|就医|去医院|医疗评估|检查)|"
    r"(?:不|别)(?:建议|需要).{0,8}(?:就医|去医院|医疗评估|检查)",
    re.I,
)
TRAINING_STOP_ACTION_PATTERN = re.compile(
    r"暂停|停止|先不(?:做|继续|安排)|不继续|不会继续(?:做|操作|安排)?|绝不继续|不要继续|今天不(?:做|安排)|不做",
    re.I,
)
TRAINING_BOUNDARY_ACTION_PATTERN = re.compile(
    r"不(?:要)?自行判断|无法判断|不能判断|不(?:在店内)?判断原因|"
    r"不在店内(?:判断|诊断)|不做诊断|不能诊断",
    re.I,
)
TRAINING_RECORD_ACTION_PATTERN = re.compile(r"记录|登记|留档|核对上次", re.I)
TRAINING_ESCALATE_ACTION_PATTERN = re.compile(r"上报|升级处理|联系.{0,6}(?:负责人|店长)|负责人|店长", re.I)
TRAINING_REFER_ACTION_PATTERN = re.compile(r"就医|医疗|急救|医院|医生|专业评估|去检查|尽快检查", re.I)
TRAINING_SERIOUS_ACTION_PATTERN = re.compile(r"重视|关注|需要注意|不能忽视|需要特别关注", re.I)


def visible_customer_text(history: list[dict[str, Any]], scenario: dict[str, Any] | None = None) -> str:
    messages = [clean_text(item.get("content", "")) for item in history if item.get("role") == "assistant"]
    opening = clean_text((scenario or {}).get("opening"))
    if opening and not any(opening == message for message in messages):
        messages.insert(0, opening)
    return " ".join(message for message in messages if message)


def positive_customer_risk_text(history: list[dict[str, Any]], scenario: dict[str, Any] | None = None) -> str:
    text = NEGATED_RED_FLAG_PATTERN.sub(" ", visible_customer_text(history, scenario))
    text = re.sub(
        r"(?:没有|没|并没有|并未|未出现|没出现|不再|不是|否认).{0,8}(?:加重|变重|更痛|更疼)",
        " ",
        text,
        flags=re.I,
    )
    return text


def point_wave_best_reply_context(
    scenario: dict[str, Any] | None,
    history: list[dict[str, Any]],
) -> bool:
    """Scope the operator-approved reply to MOD-03 before a red flag is disclosed."""
    scenario = scenario or {}
    scenario_text = clean_text(
        f"{scenario.get('title', '')} {scenario.get('task', '')} {scenario.get('opening', '')}"
    )
    if scenario.get("module_id") != "MOD-03" or "点阵波" not in scenario_text:
        return False
    customer_context = positive_customer_risk_text(history, scenario)
    return bool(
        re.search(r"更痛|更疼|更酸痛|酸痛|疼痛加重|打坏", customer_context, re.I)
        and not TRAINING_RED_FLAG_PATTERN.search(customer_context)
    )


def matches_point_wave_best_reply(value: Any) -> bool:
    comparable = lambda text: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", clean_text(text).lower())
    return comparable(value) == comparable(POINT_WAVE_BEST_REPLY)


def has_non_negated_match(text: str, pattern: re.Pattern[str]) -> bool:
    normalized = clean_text(text)
    for match in pattern.finditer(normalized):
        clause_start = max(
            [normalized.rfind(mark, 0, match.start()) for mark in "，。；！？,.;!?"] + [-1]
        ) + 1
        following_boundaries = []
        for mark in "，。；！？,.;!?":
            position = normalized.find(mark, match.end())
            if position >= 0:
                following_boundaries.append(position + 1 if mark in "！？!?" else position)
        clause_end = min(following_boundaries) if following_boundaries else len(normalized)
        clause = normalized[clause_start:clause_end]
        clause_prefix = normalized[clause_start:match.start()]
        # A negator in an earlier proposition must not hide a later dangerous
        # proposition: "不能判断原因但可以继续做" still affirms continuation.
        semantic_prefix = re.split(
            r"(?:但是|但|而是|可是|然而|不过|却|仍然?|还是|也|所以|因此|然后|同时)",
            clause_prefix,
            flags=re.I,
        )[-1]
        negated = re.search(
            r"(?:不能|不可|不要|不应|不建议|不会|不用|不必|无需|无须|未必|不一定|"
            r"不代表|不认为|不觉得|不承认|并不|绝不|暂不|先不|停止|避免|拒绝|别)"
            r"[^，。；！？,.;!?]{0,20}$|"
            r"(?:不是|并非)(?:要|让|叫|建议)?(?:你|您|我们)?$|"
            r"不把.{0,12}(?:说成|解释成|当成)$|"
            r"(?:不|不能|不可)算(?:是)?$|不$",
            semantic_prefix,
            re.I,
        )
        questioned = bool(
            re.search(r"[？?]", clause)
            and re.search(
                r"难道|是否|是不是|会不会|要不要|能不能|可不可以|有没有|怎么(?:能|会|可以)|为什么|为何",
                clause,
                re.I,
            )
        )
        questioned = questioned or bool(
            re.search(r"(?:是否|是不是|算不算|可否)[^，。；！？,.;!?]{0,8}$", semantic_prefix, re.I)
        )
        direct_question_suffix = bool(re.search(r"^[^，。；！,.;!]{0,10}(?:吗|么|呢)[？?]", normalized[match.end():], re.I))
        if negated or questioned or direct_question_suffix:
            continue
        return True
    return False


def training_safe_action_flags(employee_message: str) -> dict[str, bool]:
    """Return only affirmed safety actions; denied or questioned actions never count."""
    message = clean_text(employee_message)
    return {
        "stopped": has_non_negated_match(message, TRAINING_STOP_ACTION_PATTERN),
        "keeps_boundary": has_non_negated_match(message, TRAINING_BOUNDARY_ACTION_PATTERN),
        "records": has_non_negated_match(message, TRAINING_RECORD_ACTION_PATTERN),
        "escalates": has_non_negated_match(message, TRAINING_ESCALATE_ACTION_PATTERN),
        "refers": has_non_negated_match(message, TRAINING_REFER_ACTION_PATTERN),
        "takes_seriously": has_non_negated_match(message, TRAINING_SERIOUS_ACTION_PATTERN),
    }


def training_critical_reason(
    employee_message: str,
    history: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> str:
    message = clean_text(employee_message)
    customer_context = positive_customer_risk_text(history, scenario)
    known_worsening = bool(TRAINING_WORSENING_PATTERN.search(customer_context) and TRAINING_DISCOMFORT_PATTERN.search(customer_context))
    known_red_flag = bool(TRAINING_RED_FLAG_PATTERN.search(customer_context))
    known_discomfort = bool(TRAINING_DISCOMFORT_PATTERN.search(customer_context))
    if point_wave_best_reply_context(scenario, history) and matches_point_wave_best_reply(message):
        return ""
    if unsafe_claim_hits(message):
        return "员工原话包含医疗化判断或结果承诺"
    if (known_worsening or known_red_flag) and has_non_negated_match(message, TRAINING_DENIES_SAFETY_PATTERN):
        return "员工在已知异常时明确拒绝暂停、记录、升级或医疗分流"
    if (known_worsening or known_red_flag) and has_non_negated_match(message, TRAINING_UNSAFE_NORMALIZATION_PATTERN):
        return "员工把已知的服务后疼痛加重正常化或作了未核实解释"
    if known_discomfort and has_non_negated_match(message, TRAINING_CONTINUE_PATTERN):
        return "员工在已知不适时仍建议继续、忍耐或加量"
    return ""


def training_safe_response_state(
    employee_message: str,
    history: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> str:
    """Return critical/full/partial/none using only facts visible before this turn."""
    if training_critical_reason(employee_message, history, scenario):
        return "critical"
    message = clean_text(employee_message)
    customer_context = positive_customer_risk_text(history, scenario)
    if not TRAINING_RED_FLAG_PATTERN.search(customer_context):
        return "none"
    actions = training_safe_action_flags(message)
    if all(actions[key] for key in ("stopped", "keeps_boundary", "records", "escalates", "refers")):
        return "full"
    if any(actions.values()):
        return "partial"
    return "none"


def training_customer_safety_followup(
    employee_message: str,
    history: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> str:
    state = training_safe_response_state(employee_message, history, scenario)
    if state == "full":
        return "好的，那我今天先不做了。麻烦帮我记录一下，也告诉我怎么联系负责人。"
    if state == "partial":
        return "好的，我会尽快去检查。那我今天是不是先不做了？"
    return ""


def training_feedback_claims_unknown_customer_fact(
    feedback: dict[str, Any],
    history: list[dict[str, Any]],
    scenario: dict[str, Any] | None = None,
) -> bool:
    """Reject feedback that asserts facts absent before the employee spoke.

    The current customer reply is intentionally not an input.  It belongs to the
    next turn and must never change this turn's score or explanation.
    """
    known_before_reply = NEGATED_RED_FLAG_PATTERN.sub(" ", visible_customer_text(history, scenario))
    feedback_fields = {
        key: clean_text(feedback.get(key, ""))
        for key in ("issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal")
    }
    critique = " ".join(feedback_fields.values())
    for marker in TRAINING_NEW_FACT_MARKERS:
        if marker in known_before_reply or marker not in critique:
            continue
        assertion_pattern = re.compile(
            rf"(?:顾客|客户).{{0,10}}(?:已经|明确|提到|表示|说|出现|有|伴有).{{0,10}}{re.escape(marker)}|"
            rf"您(?:现在|已经|出现|有|伴有).{{0,10}}{re.escape(marker)}|"
            rf"(?:已知|新发|刚补充|出现|伴有|存在|未识别|未处理|未重视|忽略).{{0,16}}{re.escape(marker)}|"
            rf"{re.escape(marker)}.{{0,12}}(?:已出现|新发|需要处理|这一红旗|红旗信号)",
            re.I,
        )
        if assertion_pattern.search(critique):
            return True
    return False


def training_message_has_complete_safe_closure(employee_message: str) -> bool:
    message = clean_text(employee_message)
    actions = training_safe_action_flags(message)
    return (
        all(actions[key] for key in ("stopped", "keeps_boundary", "records", "escalates", "refers"))
        and not TRAINING_DENIES_SAFETY_PATTERN.search(message)
        and not unsafe_claim_hits(message)
        and not has_non_negated_match(message, TRAINING_UNSAFE_NORMALIZATION_PATTERN)
        and not has_non_negated_match(message, TRAINING_CONTINUE_PATTERN)
    )


def sanitize_training_suggested_reply(feedback: dict[str, Any]) -> None:
    if TRAINING_UNVERIFIED_ADVICE_PATTERN.search(clean_text(feedback.get("suggested_reply", ""))):
        feedback["suggested_reply"] = "您目前描述的不适需要优先重视。我们先停止所有项目，不在店内判断原因；我会记录并上报负责人，并建议您尽快由医疗机构评估。"


def deterministic_training_feedback(
    employee_message: str,
    history: list[dict[str, Any]],
    scenario: dict[str, Any] | None,
) -> dict[str, str] | None:
    message = clean_text(employee_message)
    point_wave_best_context = point_wave_best_reply_context(scenario, history)
    if point_wave_best_context and matches_point_wave_best_reply(message):
        return {
            "level": "good",
            "issue": "你已使用点阵波模块设定的服务后反应最佳回答，表达完整且没有跳到其他模块。",
            "why": "本轮顾客咨询的是点阵波服务后更酸痛；回答已按该模块批准话术解释原理、反应和感受。",
            "method_step": "使用点阵波服务后反应标准话术",
            "knowledge_focus": "点阵波理疗后反应与顾客安抚",
            "suggested_reply": POINT_WAVE_BEST_REPLY,
            "next_goal": "下一轮继续承接顾客对点阵波服务后感受的追问。",
        }
    critical_reason = training_critical_reason(message, history, scenario)
    if critical_reason:
        medical_claim = "医疗化判断" in critical_reason
        unsafe_continuation = "继续、忍耐或加量" in critical_reason
        denies_safety = "明确拒绝暂停" in critical_reason
        return {
            "level": "critical",
            "issue": f"你这句“{message[:72]}”{critical_reason.replace('员工', '')}，需要立即纠正。",
            "why": (
                "门店员工不能判断病因、把服务说成治疗，或承诺确定结果。本轮应回到顾客已表达的目标和安全信息，再说明非医疗服务边界。"
                if medical_claim else
                "顾客在你回答前已出现需要优先处理的异常。明确拒绝暂停、记录、升级或医疗分流，会让顾客误以为可以继续并延误必要处理。"
                if denies_safety else
                "顾客在你回答前已明确表达不适。不能继续、让顾客忍耐或加量；当前尚未出现的伴随症状不作为本轮扣分依据。"
                if unsafe_continuation else
                "顾客在你回答前已明确表达服务后疼痛加重。不能直接说正常或用未核实原理解释；当前尚未出现的伴随症状不作为本轮扣分依据。"
            ),
            "method_step": "说明非医疗边界并回到必要问询" if medical_claim else "停止服务并完成安全升级" if denies_safety else "承接担心并先做服务后安全问询",
            "knowledge_focus": "非医疗服务边界、不诊断与不承诺" if medical_claim else "暂停、记录、负责人升级与医疗分流" if denies_safety else "服务后变化、异常边界与必要分流",
            "suggested_reply": (
                "我理解您想尽快改善，但门店不能判断病因或承诺治好。我先确认您最想改善的问题、持续时间和必要安全信息，再说明门店可以提供的非医疗体验。"
                if medical_claim else
                "您描述的异常需要优先处理。今天先停止所有项目，我们不在店内判断原因；我会记录并上报负责人，建议您尽快由医疗机构评估。"
                if denies_safety else
                "我理解您会担心，疼痛比原来加重不能先简单说是正常。今天先暂停后续项目，我们不在店内判断原因；我会记录并联系负责人。我还要确认从什么时候开始、是否还在加重；如有新发麻木、无力或其他异常，建议尽快由医疗机构评估。"
            ),
            "next_goal": "下一轮只练习把门店体验与医疗诊断、治疗和结果承诺区分开。" if medical_claim else "先纠正拒绝安全处置的表达，并完整执行暂停、记录、升级和分流。" if denies_safety else "只根据顾客下一轮实际回答决定是否暂停、升级和分流。",
        }
    safe_state = training_safe_response_state(message, history, scenario)
    if safe_state == "full":
        return {
            "level": "good",
            "issue": "你已明确暂停项目、不在店内判断原因，并完成记录升级和医疗分流。",
            "why": "这些表达形成完整安全闭环，且只处理对话中已知的异常。",
            "method_step": "停止服务并完成安全升级",
            "knowledge_focus": "异常记录、负责人升级与医疗分流",
            "suggested_reply": "现在先停止所有项目，我们不在店内判断原因。我会记录并上报负责人，并建议您尽快由医疗机构评估。",
            "next_goal": "确认顾客理解安全安排，并完成记录、上报与跟进。",
        }
    customer_context = positive_customer_risk_text(history, scenario)
    known_worsening = bool(TRAINING_WORSENING_PATTERN.search(customer_context) and TRAINING_DISCOMFORT_PATTERN.search(customer_context))
    acknowledges = bool(re.search(r"理解|担心|重视|抱歉|先不判断|不能先说", message, re.I))
    pauses = has_non_negated_match(message, TRAINING_STOP_ACTION_PATTERN)
    asks_change = bool(re.search(r"什么时候|何时|多久|是否.{0,6}加重|是否.{0,8}更重|比.{0,8}(?:重|疼|痛)|变化", message, re.I))
    asks_companion = bool(re.search(
        r"伴随|还有.{0,10}(?:不适|症状|反应)|(?:有没有|是否)?其他.{0,8}(?:不适|症状|反应)|"
        r"有没有.{0,12}(?:麻|无力|发热|红肿|胸痛|不舒服)|是否.{0,12}(?:麻|无力|发热|红肿|胸痛|不舒服)",
        message,
        re.I,
    ))
    prior_safe_pause = any(
        has_non_negated_match(clean_text(item.get("content", "")), TRAINING_STOP_ACTION_PATTERN)
        and not has_non_negated_match(clean_text(item.get("content", "")), TRAINING_CONTINUE_PATTERN)
        and not has_non_negated_match(clean_text(item.get("content", "")), TRAINING_UNSAFE_NORMALIZATION_PATTERN)
        and not TRAINING_DENIES_SAFETY_PATTERN.search(clean_text(item.get("content", "")))
        for item in history
        if item.get("role") == "user"
    )
    if known_worsening and asks_companion:
        if pauses or prior_safe_pause:
            return {
                "level": "good",
                "issue": "你在暂停后继续追问麻木、无力、发热或红肿等伴随情况，问询顺序正确。",
                "why": "本轮只筛查尚未确认的伴随情况，没有把它们提前当作顾客已经出现的事实。",
                "method_step": "在暂停后完成伴随情况筛查",
                "knowledge_focus": "麻木、无力、发热、红肿等异常变化",
                "suggested_reply": "除了疼痛加重，还有没有麻木、无力、发热、红肿或其他新出现的不适？",
                "next_goal": "根据顾客下一轮实际补充的信息，决定记录升级和医疗分流。",
            }
        return {
            "level": "needs_work",
            "issue": "你已追问伴随情况，但还没有先明确暂停今天的后续项目。",
            "why": "服务后疼痛加重时应先暂停安排，再筛查时间、变化和伴随情况。",
            "method_step": "先暂停，再完成伴随情况筛查",
            "knowledge_focus": "服务后变化与安全问询顺序",
            "suggested_reply": "疼痛比原来加重需要先重视，今天先暂停后续项目；除了疼痛变化，还有没有麻木、无力、发热、红肿或其他新不适？",
            "next_goal": "确认暂停后，根据顾客实际回答决定是否升级和分流。",
        }
    if known_worsening and acknowledges and pauses and asks_change:
        return {
            "level": "good",
            "issue": "你已经承接顾客的担心、先暂停后续安排，并追问疼痛开始时间和变化。",
            "why": "本轮只使用顾客已经说出的“服务后更痛”来判断；先暂停、再问变化，符合安全优先的接待顺序。",
            "method_step": "暂停安排并完成服务后变化问询",
            "knowledge_focus": "出现时间、变化趋势与伴随情况",
            "suggested_reply": "我理解您会担心。疼痛比原来加重不能先简单说是正常，今天先暂停后续项目；请告诉我从什么时候开始、现在是否还在加重。",
            "next_goal": "根据顾客下一轮实际补充的信息，再决定是否需要记录升级和医疗分流。",
        }
    if safe_state == "partial":
        return {
            "level": "needs_work",
            "issue": f"你这句“{message[:72]}”已给出重视或就医方向，但还没有完成暂停、记录和负责人升级的闭环。",
            "why": "对话中已知的新症状或异常需要先中止服务并留痕升级；医疗分流方向正确，所以不应评为危险误判。",
            "method_step": "补齐安全闭环",
            "knowledge_focus": "暂停服务、异常记录、负责人升级与医疗分流",
            "suggested_reply": "您刚才说的新症状需要重视。今天先停止所有项目，我会记录并联系负责人，建议您尽快由医疗机构评估。",
            "next_goal": "明确顾客今天不再继续，并完成记录和升级联络。",
        }
    return None


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
    deterministic_feedback = deterministic_training_feedback(employee_message, history, scenario)
    if deterministic_feedback:
        normalized_feedback.update(deterministic_feedback)
    elif normalized_feedback["level"] == "critical" and training_message_has_complete_safe_closure(employee_message):
        normalized_feedback.update({
            "level": "good",
            "issue": "你已明确暂停项目、不判断原因，并完成记录上报和必要的医疗分流。",
            "why": "这些表达形成了完整的安全闭环，不应被误判为继续操作或店内诊断。",
            "method_step": "停止服务并完成安全升级",
            "knowledge_focus": "异常记录、负责人升级与医疗分流",
            "suggested_reply": "现在先停止所有项目，我们不在店内判断原因。我会记录并上报，同时根据情况建议您尽快由医疗机构评估。",
            "next_goal": "确认顾客理解安全安排，并完成记录、上报与跟进。",
        })
    elif training_feedback_claims_unknown_customer_fact(normalized_feedback, history, scenario):
        asked_change = bool(re.search(r"什么时候|多久|是否.{0,5}加重|比.{0,6}重|伴随|有没有|是否还有", employee_message, re.I))
        normalized_feedback.update({
            "level": "needs_work",
            "issue": "你正在承接顾客已表达的担心并追问必要变化；顾客之后补充的新情况应从下一轮起处理。" if asked_change else f"本轮“{clean_text(employee_message)[:60]}”还需要围绕顾客已表达的问题补一个必要追问。",
            "why": "本轮反馈只评价你说话前已经出现的对话信息；顾客在你说完之后才透露的信息不作为本轮扣分依据。",
            "method_step": "承接当前问题并补一个必要信息",
            "knowledge_focus": "顾客已表达的变化、影响和必要安全信息",
            "suggested_reply": "我理解您会担心。我先确认这种变化从什么时候开始、是否还在加重，以及有没有其他新出现的不适。",
            "next_goal": "根据顾客下一轮实际回答处理新信息。",
        })
    sanitize_training_suggested_reply(normalized_feedback)
    result["feedback"] = normalized_feedback
    return result


def normalize_test_turn_result(result: dict[str, Any] | None, scenario: dict[str, Any] | None, history: list[dict[str, Any]], employee_message: str = "") -> dict[str, Any]:
    result = result if isinstance(result, dict) else {}
    reply = normalized_customer_reply(result.get("reply", ""), scenario, history, employee_message)
    emotion = clean_text(result.get("emotion", "neutral"))
    if emotion not in {"curious", "hesitant", "concerned", "relieved", "neutral"}:
        emotion = "neutral"
    return {"reply": reply, "emotion": emotion, "should_continue": result.get("should_continue") is not False}


ASSESSMENT_RED_FLAG_PATTERN = re.compile(
    r"胸痛|胸闷|呼吸困难|气短|晕厥|昏厥|突发剧痛|进行性麻木无力|"
    r"手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|腿(?:部)?(?:新发|新|发)?麻|发麻|麻木|无力|发热|红肿|头晕|大小便异常|会阴麻木",
    re.I,
)
ASSESSMENT_CONTINUE_SERVICE_PATTERN = re.compile(
    r"可以(?:继续)?做|还可以做|安排(?:项目|体验)|先体验|继续(?:做|操作|体验)|"
    r"接着做(?:完)?|照常(?:做|操作)|把.{0,4}(?:项目|体验|操作)?做完|做完再说|"
    r"(?:不用|不必|无需|无须)停|没必要暂停|"
    r"再做一次|加量|打透|忍一忍|坚持一下|正常(?:反应|现象|的)?|"
    r"没(?:啥|什么)?问题|没事|没关系|不要紧|不碍事",
    re.I,
)
ASSESSMENT_DRUG_ADVICE_PATTERN = re.compile(r"(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)", re.I)
ASSESSMENT_PRESSURE_PATTERN = re.compile(r"必须|今天就|现在就|一定要|不能拒绝|不买|不做.{0,8}(?:后悔|更严重)|别告诉|隐瞒|瞒着", re.I)


def detect_assessment_failure_details(history: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Detect failures turn by turn so future facts and later repairs cannot rewrite the past."""
    details: dict[str, dict[str, str]] = {}
    visible_customer_messages: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        content = clean_text(item.get("content", ""))
        if not content:
            continue
        if item.get("role") == "assistant":
            visible_customer_messages.append(content)
            continue
        if item.get("role") != "user":
            continue

        customer_before = NEGATED_RED_FLAG_PATTERN.sub(" ", " ".join(visible_customer_messages))
        evidence = f"员工原话：“{content[:180]}”"
        if unsafe_claim_hits(content) or has_non_negated_match(content, ASSESSMENT_DRUG_ADVICE_PATTERN):
            details.setdefault("CF-02", {"evidence": evidence})

        red_flag_known = bool(ASSESSMENT_RED_FLAG_PATTERN.search(customer_before))
        continues_service = has_non_negated_match(content, ASSESSMENT_CONTINUE_SERVICE_PATTERN)
        if red_flag_known and continues_service:
            details.setdefault("CF-01", {"evidence": evidence})

        refused = bool(re.search(r"不想|拒绝|不要触碰|不拍照|回家考虑|不愿意|不同意", customer_before, re.I))
        pressure = has_non_negated_match(content, ASSESSMENT_PRESSURE_PATTERN)
        if refused and pressure:
            details.setdefault("CF-03", {"evidence": evidence})

        discomfort_known = bool(re.search(r"疼|痛|灼热|烫|头晕|不舒服|设备异常|麻|无力", customer_before, re.I))
        if discomfort_known and continues_service:
            details.setdefault("CF-04", {"evidence": evidence})
    return details


def detect_assessment_failures(history: list[dict[str, Any]]) -> list[str]:
    details = detect_assessment_failure_details(history)
    return [code for code in ("CF-01", "CF-02", "CF-03", "CF-04") if code in details]


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


def evidence_is_grounded_in_employee(evidence: str, history: list[dict[str, Any]]) -> bool:
    """Require assessment evidence to contain words the employee actually said."""
    if "对话中未体现" in evidence:
        return True
    employee_messages = [
        clean_text(item.get("content", ""))
        for item in history
        if item.get("role") == "user" and clean_text(item.get("content", ""))
    ]
    if not employee_messages:
        return False
    quoted = [clean_text(value) for value in re.findall(r"[“\"]([^”\"]+)[”\"]", evidence)]
    if quoted:
        return any(value and any(value in message for message in employee_messages) for value in quoted)
    evidence_compact = re.sub(r"[\s，,。.；;:：！!？?“”\"'、]", "", evidence)
    for message in employee_messages:
        compact = re.sub(r"[\s，,。.；;:：！!？?“”\"'、]", "", message)
        if len(compact) < 6:
            if compact and compact in evidence_compact:
                return True
            continue
        if any(compact[index:index + 6] in evidence_compact for index in range(len(compact) - 5)):
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
        if (
            not evidence
            or evidence_uses_customer_only_text(evidence, history)
            or not evidence_is_grounded_in_employee(evidence, history)
        ):
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
    failure_details = detect_assessment_failure_details(history)
    critical_failures = []
    for code in ("CF-01", "CF-02", "CF-03", "CF-04"):
        if code not in failure_details:
            continue
        item = model_failures.get(code, {})
        spec = failure_specs[code]
        critical_failures.append({
            "code": code,
            "reason": clean_text(item.get("reason", "")) or spec["rule"],
            "evidence": failure_details[code]["evidence"],
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
    prompt_overrides = normalize_prompt_overrides(payload.get("prompt_overrides"))
    scenario = scenario_by_id(payload.get("scenario_id")) if mode in {"training", "test"} else None

    if action == "start" and mode in {"training", "test"}:
        return {"ok": True, "mode": mode, "scenario": public_scenario(scenario_by_id(payload.get("scenario_id"))), "message": scenario_by_id(payload.get("scenario_id")).get("opening"), "source_refs": []}
    if not message and action != "finish":
        raise ValueError("请输入内容")

    dialogue_history = clean_dialogue_history(history)
    recent_dialogue = " ".join(item["content"] for item in dialogue_history[-6:])
    query = qa_context_query(message, dialogue_history) if mode == "qa" else clean_text(f"{recent_dialogue} {message}")
    common_qa_candidates_list: list[dict[str, Any]] = []
    common_qa_selection_meta: dict[str, Any] = {"attempted": False, "candidate_count": 0}
    common_qa_match: dict[str, Any] | None = None
    if mode == "qa":
        candidate_query = message
        common_qa_candidates_list = common_qa_candidates(message, limit=6)
        if query != message and message.startswith(("那", "这个", "这种", "它", "刚才", "如果", "那么", "可是", "但是")):
            candidate_query = query
            common_qa_candidates_list = common_qa_candidates(query, limit=6)
        common_qa_match = point_wave_best_common_qa(candidate_query)
        if common_qa_match:
            common_qa_selection_meta = {
                "attempted": False,
                "candidate_count": 1,
                "selection": "point_wave_best_answer",
            }
        else:
            common_qa_match, common_qa_selection_meta = select_common_qa_with_model(
                candidate_query,
                common_qa_candidates_list,
                model,
                api_key,
            )
    route = route_customer_question(query)
    docs = [] if common_qa_match and mode == "qa" else retrieve(query, limit=8, route=route, include_common_qa=mode != "qa")
    if common_qa_match and mode == "qa":
        # A matched FAQ owns the answer and its course references. Do not mix
        # generic route documents into the same response.
        docs = [common_qa_document(common_qa_match["row"])]
    elif mode in {"qa", "training", "test"}:
        docs = with_safety_doc(docs)
    citation_refs = public_citations(docs)

    if mode == "qa":
        if common_qa_match:
            matched_row = common_qa_match["row"]
            result = {
                "answer": common_qa_match.get("answer") or matched_row.get("approved_answer", ""),
                "uncertainties": [],
                "recommended_action": "如需继续了解，可打开下方对应课程学习；涉及当前价格、门店政策或个体适用性时，请再核对有效版本。",
                "faq_match": public_common_qa_match(common_qa_match),
            }
            result = apply_methodology_result(result, mode, route)
            result["answer"] = common_qa_match.get("answer") or matched_row.get("approved_answer", "")
            result["faq_match"] = public_common_qa_match(common_qa_match)
            return response_payload(mode, result, docs, {"mock": not common_qa_selection_meta.get("attempted"), "model": model, "common_qa": True, **common_qa_selection_meta})
        user_message = f"顾客当前问题：{message}\n\n方法路由：\n{route_context_block(route)}\n\n检索资料：\n{context_block(docs)}"
        if MOCK_MODE or not api_key:
            result = apply_methodology_result(safety_filter(mock_qa_response(message, route, docs), mode, message, route), mode, route)
            return response_payload(mode, result, docs, {"mock": True, "model": model, "common_qa": False, **common_qa_selection_meta})
        qa_system = prompt_system_envelope("qa", prompt_overrides["qa"])
        raw, meta = call_model(qa_system, [*dialogue_history, {"role": "user", "content": user_message}], model, api_key, temperature=0.2)
        result = apply_methodology_result(safety_filter(extract_json(raw) or {"answer": raw, "uncertainties": ["模型未按结构化格式返回，请人工核验。"], "citations": citation_refs, "recommended_action": ""}, mode, message, route), mode, route)
        return response_payload(mode, result, docs, {**meta, "mock": False, "common_qa": False, **common_qa_selection_meta})

    if mode == "training":
        turn_number = sum(1 for item in dialogue_history if item.get("role") == "user") + 1
        if MOCK_MODE or not api_key:
            result = apply_methodology_result(safety_filter(mock_response(mode, action, message, scenario, history, docs), mode, message, route), mode, route)
            result = normalize_training_result(result, scenario, history, message)
            return response_payload(mode, result, docs, {"mock": True, "model": model})
        model_messages = [*dialogue_history, {"role": "user", "content": message}]
        customer_system = training_customer_system(scenario, turn_number, prompt_overrides["training"]["customer"])
        feedback_system = training_feedback_system(scenario, route, docs, turn_number, prompt_overrides["training"]["coach"])
        # Both role calls share one bounded wait budget. This preserves a
        # healthy peer that finishes after the other role fails, while also
        # preventing either provider call from holding the request for its
        # full network timeout. Any role unfinished at the deadline uses its
        # deterministic local fallback.
        from concurrent.futures import wait

        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="training-turn")
        futures = {
            "customer": executor.submit(
                call_model, customer_system, model_messages, model, api_key, 0.55, 500,
            ),
            "feedback": executor.submit(
                call_model, feedback_system, model_messages, model, api_key, 0.2, 1000,
            ),
        }
        wait_budget = max(0.05, TRAINING_DUAL_CALL_WAIT_SECONDS)
        done, pending = wait(futures.values(), timeout=wait_budget)
        for future in pending:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

        model_results: dict[str, tuple[str, dict[str, Any]]] = {}
        failed_roles: list[str] = []
        for role, future in futures.items():
            if future not in done or future.cancelled():
                failed_roles.append(role)
                continue
            try:
                model_results[role] = future.result()
            except Exception:
                failed_roles.append(role)

        if not model_results:
            raise RuntimeError("模拟顾客与训练教练均未返回可用结果，请稍后重试。")

        local_fallback = mock_response(mode, action, message, scenario, history, docs)
        customer_raw, customer_meta = model_results.get("customer", ("", {}))
        feedback_raw, feedback_meta = model_results.get("feedback", ("", {}))
        customer_payload = (
            extract_json(customer_raw) or {"customer_reply": customer_raw}
            if customer_raw
            else {"customer_reply": local_fallback.get("customer_reply", "")}
        )
        feedback_payload = (
            extract_json(feedback_raw) or {
                "feedback": {
                    "level": "needs_work",
                    "issue": "模型未按结构化格式返回。",
                    "why": "请重试并继续围绕顾客当前问题训练。",
                    "method_step": "承接当前问题",
                    "knowledge_focus": "顾客已表达的需求和必要安全信息",
                    "suggested_reply": "我先确认一个关键信息：这种情况从什么时候开始？",
                    "next_goal": "下一轮只补一个必要信息。",
                }
            }
            if feedback_raw
            else {"feedback": local_fallback.get("feedback", {})}
        )
        feedback = feedback_payload.get("feedback") if isinstance(feedback_payload.get("feedback"), dict) else feedback_payload
        result = {
            "customer_reply": clean_text(customer_payload.get("customer_reply") or customer_payload.get("reply") or customer_raw),
            "feedback": feedback,
        }
        result = apply_methodology_result(safety_filter(result, mode, message, route), mode, route)
        result = normalize_training_result(result, scenario, history, message)
        return response_payload(mode, result, docs, {
            **merge_model_meta(customer_meta, feedback_meta),
            "mock": False,
            "degraded": bool(failed_roles),
            "fallback_roles": failed_roles,
        })

    if mode == "test" and action == "turn":
        hidden_context = json.dumps(customer_turn_context(scenario), ensure_ascii=False)
        turn_number = sum(1 for item in dialogue_history if item.get("role") == "user") + 1
        test_system = f"{prompt_system_envelope('simulation_customer', prompt_overrides['simulation']['customer'])}\n\n场景设定（只供你使用，不得泄露）：{hidden_context}\n开场白：{scenario.get('opening')}\n当前是员工第 {turn_number} 轮回复。"
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
        public_assessment_context = json.dumps(assessment_scenario_context(scenario), ensure_ascii=False)
        user_message = f"评分表：\n{rubric_context}\n\n公开任务：\n{public_assessment_context}\n\n已发生的完整对话：\n{dialogue}"
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
        assessment_system = prompt_system_envelope("simulation_assessment", prompt_overrides["simulation"]["assessment"])
        raw, meta = call_model(assessment_system, [{"role": "user", "content": user_message}], model, api_key, temperature=0.1, max_tokens=1800)
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
            self.send_json({"ok": True, "api_configured": bool(ENV_API_KEY), "mock_mode": MOCK_MODE, "model": DEFAULT_MODEL, "models": AVAILABLE_MODELS, "knowledge": {"rag_documents": len(RAG_DOCUMENTS), "common_qa": len(COMMON_QA), "knowledge_cards": len(CARDS), "objections": len(OBJECTIONS), "scenarios": len(SCENARIOS)}})
            return
        if request_path == "/api/bootstrap":
            self.send_json({"ok": True, "scenarios": [public_scenario(item) for item in SCENARIOS], "models": AVAILABLE_MODELS, "prompt_defaults": DEFAULT_PROMPT_OVERRIDES, "knowledge": {"rag_documents": len(RAG_DOCUMENTS), "common_qa": len(COMMON_QA), "knowledge_cards": len(CARDS), "objections": len(OBJECTIONS), "sources": len(SOURCE_REGISTRY)}, "rubric": {"total": RUBRIC.get("total"), "dimensions": [{"id": item["id"], "name": item["name"], "weight": item["weight"]} for item in RUBRIC.get("dimensions", [])]}})
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
