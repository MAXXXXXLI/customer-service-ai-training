from __future__ import annotations

import json
import re
from pathlib import Path

from server import qa_context_query, route_customer_question


CASES = [
    {
        "name": "red_flag_stops_sales",
        "question": "我最近胸闷气短还出冷汗，今天先做个超V可以吗？",
        "primary": "MOD-01",
        "supports": [],
        "stop_sales": True,
    },
    {
        "name": "post_service_discomfort",
        "question": "昨天做完今天更痛还头晕，是不是说明有效？",
        "primary": "MOD-01",
        "supports": [],
        "stop_sales": True,
    },
    {
        "name": "diagnosed_numbness_cannot_be_surgery_substitute",
        "question": "我腰椎间盘突出而且腿麻，你们的点阵波能替代手术吗？",
        "primary": "MOD-01",
        "supports": ["MOD-03"],
        "stop_sales": True,
    },
    {
        "name": "pain_project",
        "question": "点阵波做肩颈是什么感受？",
        "primary": "MOD-03",
        "supports": [],
        "stop_sales": False,
    },
    {
        "name": "negated_red_flags_do_not_stop_sales",
        "question": "顾客最近肩颈酸痛，但没有麻木或无力，点阵波是否适合？",
        "primary": "MOD-03",
        "supports": ["MOD-01"],
        "stop_sales": False,
        "intent": "适用性、安全与体验感受",
    },
    {
        "name": "pain_result_count_is_not_price",
        "question": "点阵波一般做几次才能好？",
        "primary": "MOD-03",
        "supports": ["MOD-01"],
        "stop_sales": False,
        "intent": "效果、次数、速度与结果承诺",
    },
    {
        "name": "beauty_suitability",
        "question": "敏感肌最近有点泛红，水光能不能做？",
        "primary": "MOD-09",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-038",
    },
    {
        "name": "slimming_result_objection",
        "question": "减肥能保证一个月瘦十斤不反弹吗？",
        "primary": "MOD-05",
        "supports": [],
        "stop_sales": False,
    },
    {
        "name": "drug_special_population",
        "question": "我有糖尿病，GLP-1怎么用、剂量多少？",
        "primary": "MOD-06",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-026",
    },
    {
        "name": "nutrition_weight_management",
        "question": "饮食和运动怎么管理体重？",
        "primary": "MOD-05",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-020",
    },
    {
        "name": "meitomer_nutrition_support",
        "question": "美妥是什么？",
        "primary": "MOD-05",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-024",
    },
    {
        "name": "ice_sculpting_local_contouring",
        "question": "冰雕是什么项目？",
        "primary": "MOD-07",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-030",
    },
    {
        "name": "product_184",
        "question": "184饱腹产品是什么？",
        "primary": "MOD-07",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-029",
    },
    {
        "name": "custom_underwear",
        "question": "定制内衣怎么量体？",
        "primary": "MOD-07",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-031",
    },
    {
        "name": "nano_spray_skin_care",
        "question": "纳米喷射是什么项目？",
        "primary": "MOD-08",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-034",
    },
    {
        "name": "smart_lift_device",
        "question": "智能提拉是什么项目？",
        "primary": "MOD-08",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-035",
    },
    {
        "name": "hair_follicle_care",
        "question": "毛囊和头皮养护是什么？",
        "primary": "MOD-08",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-037",
    },
    {
        "name": "thermage_face_aesthetics",
        "question": "热玛吉是什么项目？",
        "primary": "MOD-09",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-040",
    },
    {
        "name": "hyaluronic_face_support",
        "question": "玻尿酸和面部凹陷有什么关系？",
        "primary": "MOD-09",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-042",
    },
    {
        "name": "pelvic_floor_private_health",
        "question": "盆底服务是什么？",
        "primary": "MOD-10",
        "supports": [],
        "stop_sales": False,
        "required_course": "COURSE-NKB-043",
    },
    {
        "name": "dynamic_price",
        "question": "成都这家店的超V今天多少钱，有活动吗？",
        "primary": "MOD-02",
        "supports": [],
        "stop_sales": False,
    },
    {
        "name": "vague_new_customer",
        "question": "我第一次来，不知道适合什么，你帮我看看。",
        "primary": "MOD-02",
        "supports": [],
        "stop_sales": False,
    },
]


results = []
for case in CASES:
    route = route_customer_question(case["question"])
    missing_supports = [item for item in case["supports"] if item not in route["support_module_ids"]]
    passed = (
        route["primary_module_id"] == case["primary"]
        and not missing_supports
        and route["stop_sales"] is case["stop_sales"]
        and (not case.get("intent") or route["intent_label"] == case["intent"])
        and (not case.get("required_course") or case["required_course"] in route["required_course_ids"])
        and bool(route["required_course_ids"])
        and bool(route["method_step"])
    )
    results.append({
        "name": case["name"],
        "passed": passed,
        "actual_primary": route["primary_module_id"],
        "actual_supports": route["support_module_ids"],
        "actual_stop_sales": route["stop_sales"],
        "intent": route["intent_label"],
        "courses": route["required_courses"],
    })

follow_up_query = qa_context_query(
    "她追问一般做几次才能好，该怎么回答？",
    [
        {"role": "user", "content": "顾客最近肩颈酸痛，但没有麻木或无力，点阵波是否适合？"},
        {"role": "assistant", "content": "需要先完成安全确认。"},
    ],
)
follow_up_route = route_customer_question(follow_up_query)
results.append({
    "name": "natural_follow_up_keeps_previous_topic",
    "passed": (
        follow_up_route["intent_label"] == "效果、次数、速度与结果承诺"
        and follow_up_route["primary_module_id"] == "MOD-03"
        and not follow_up_route["stop_sales"]
    ),
    "actual_primary": follow_up_route["primary_module_id"],
    "actual_supports": follow_up_route["support_module_ids"],
    "actual_stop_sales": follow_up_route["stop_sales"],
    "intent": follow_up_route["intent_label"],
    "courses": follow_up_route["required_courses"],
})


METHODOLOGY_PATH = Path(__file__).resolve().parents[1] / "knowledge_base" / "customer_service_methodology.json"
methodology = json.loads(METHODOLOGY_PATH.read_text(encoding="utf-8"))
topic_routes = methodology["topic_routes"]

TOPIC_TAXONOMY = [
    {
        "id": "TOPIC-GLP",
        "module": "MOD-06",
        "courses": {"COURSE-NKB-026", "COURSE-NKB-027", "COURSE-NKB-028"},
        "terms": ["GLP-1", "贝那鲁肽", "司美格鲁肽", "利拉鲁肽", "减肥针"],
    },
    {
        "id": "TOPIC-SLIMMING-PRODUCTS",
        "module": "MOD-07",
        "courses": {"COURSE-NKB-029", "COURSE-NKB-030", "COURSE-NKB-031", "COURSE-NKB-032"},
        "terms": ["184", "冰雕", "轰脂", "定制内衣"],
    },
    {
        "id": "TOPIC-BEAUTY",
        "module": "MOD-08",
        "courses": {"COURSE-NKB-033", "COURSE-NKB-034", "COURSE-NKB-035", "COURSE-NKB-036", "COURSE-NKB-037"},
        "terms": ["纳米喷射", "胶原微水光", "面膜", "手膜", "冰点脱毛", "毛囊", "头皮", "智能提拉", "磁波内雕"],
    },
    {
        "id": "TOPIC-FACE",
        "module": "MOD-09",
        "courses": {"COURSE-NKB-038", "COURSE-NKB-039", "COURSE-NKB-040", "COURSE-NKB-041", "COURSE-NKB-042"},
        "terms": ["热玛吉", "线雕", "Fotona", "4D", "祛斑", "玻尿酸", "肉毒", "水光", "超声炮", "射频"],
    },
    {
        "id": "TOPIC-PRIVATE",
        "module": "MOD-10",
        "courses": {"COURSE-NKB-043"},
        "terms": ["私密", "盆底"],
    },
    {
        "id": "TOPIC-SLIMMING",
        "module": "MOD-05",
        "courses": {"COURSE-NKB-020", "COURSE-NKB-021", "COURSE-NKB-022", "COURSE-NKB-023", "COURSE-NKB-024", "COURSE-NKB-025"},
        "terms": ["减重", "体重", "饮食", "营养", "运动", "美妥"],
    },
]

for expected in TOPIC_TAXONOMY:
    topic = next((item for item in topic_routes if item.get("id") == expected["id"]), None)
    patterns = topic.get("patterns", []) if topic else []
    unmatched_terms = [
        term for term in expected["terms"]
        if not any(re.search(pattern, term, flags=re.I) for pattern in patterns)
    ]
    wrong_first_topics = []
    for term in expected["terms"]:
        first = next(
            (
                item.get("id")
                for item in topic_routes
                if any(re.search(pattern, term, flags=re.I) for pattern in item.get("patterns", []))
            ),
            None,
        )
        if first != expected["id"]:
            wrong_first_topics.append({"term": term, "actual": first})
    passed = bool(topic) and (
        topic.get("module_id") == expected["module"]
        and set(topic.get("course_ids", [])) == expected["courses"]
        and not unmatched_terms
        and not wrong_first_topics
    )
    results.append({
        "name": f"taxonomy_{expected['id'].lower()}",
        "passed": passed,
        "actual_primary": topic.get("module_id") if topic else None,
        "actual_supports": [],
        "actual_stop_sales": False,
        "intent": expected["id"],
        "courses": topic.get("course_ids", []) if topic else [],
        "unmatched_terms": unmatched_terms,
        "wrong_first_topics": wrong_first_topics,
    })

report = {"status": "passed" if all(item["passed"] for item in results) else "failed", "cases": results}
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "passed" else 1)
