import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
MODULES = json.loads((ROOT / "static" / "learning_modules.json").read_text(encoding="utf-8"))["modules"]
CATALOG = json.loads((ROOT / "static" / "learning_catalog.json").read_text(encoding="utf-8"))


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


html_ids = set(re.findall(r'id="([^"]+)"', HTML))
js_id_refs = set(re.findall(r'\$\("([^"]+)"\)', JS))
health_status, health = get_json("http://127.0.0.1:8787/api/health")
bootstrap_status, bootstrap = get_json("http://127.0.0.1:8787/api/bootstrap")
scenario_ids = {item["id"] for item in bootstrap["scenarios"]}
module_scenarios = {scenario_id for module in MODULES for scenario_id in module["scenario_ids"]}
module_ids = {module["id"] for module in MODULES}
catalog_courses = CATALOG["courses"]
catalog_groups = [group for module in CATALOG["module_index"] for group in module["groups"]]
raw_title_pattern = re.compile(r"(?:SRC-\d+|CHUNK-\d+|\.(?:docx?|pptx?|xlsx?|xls|pdf|mp4)\b)", re.I)

checks = {
    "all_javascript_ids_exist": sorted(js_id_refs - html_ids) == [],
    "three_product_modes_exist": all(f'data-mode="{mode}"' in HTML for mode in ["training", "test", "qa"]),
    "module_selection_uses_dropdowns": all(f'id="{element_id}"' in HTML for element_id in ["learning-module-select", "practice-module-select", "test-module-select"]),
    "learning_and_coaching_are_separate": all(marker in HTML for marker in ['id="learning-page"', 'id="training-page"', 'data-mode="learning"', 'data-mode="training"']),
    "course_content_uses_modal": 'id="course-modal"' in HTML and 'id="course-modal-content"' in HTML,
    "qa_has_no_scenario_or_standard_panels": 'id="source-list"' not in HTML and 'id="focus-body"' not in HTML and 'id="scenario-card-body"' not in HTML,
    "finish_report_button_exists": 'id="finish-session"' in HTML,
    "seven_learning_modules": len(MODULES) == 7,
    "thirty_eight_learning_courses": len(catalog_courses) == 38,
    "twenty_one_course_chapters": len(catalog_groups) == 21,
    "course_modules_exist": {course["module_id"] for course in catalog_courses} <= module_ids,
    "every_course_has_a_chapter": all(course.get("group_id") and course.get("group_title") for course in catalog_courses),
    "course_titles_are_user_friendly": not any(raw_title_pattern.search(course["title"]) for course in catalog_courses),
    "module_scenarios_exist": module_scenarios <= scenario_ids,
    "health_endpoint": health_status == 200 and health.get("ok") is True,
    "bootstrap_endpoint": bootstrap_status == 200 and bootstrap.get("ok") is True,
}
report = {
    "status": "passed" if all(checks.values()) else "failed",
    "checks": checks,
    "details": {
        "missing_html_ids": sorted(js_id_refs - html_ids),
        "missing_scenarios": sorted(module_scenarios - scenario_ids),
        "course_count": len(catalog_courses),
        "chapter_count": len(catalog_groups),
        "model": health.get("model"),
        "api_configured": health.get("api_configured"),
    },
}
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if report["status"] == "passed" else 1)
