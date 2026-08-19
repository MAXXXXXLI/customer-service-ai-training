from __future__ import annotations

import json

from server import route_customer_question


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
        "name": "pain_project",
        "question": "点阵波做肩颈是什么感受？",
        "primary": "MOD-03",
        "supports": [],
        "stop_sales": False,
    },
    {
        "name": "beauty_suitability",
        "question": "敏感肌最近有点泛红，水光能不能做？",
        "primary": "MOD-08",
        "supports": [],
        "stop_sales": False,
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

report = {"status": "passed" if all(item["passed"] for item in results) else "failed", "cases": results}
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "passed" else 1)
