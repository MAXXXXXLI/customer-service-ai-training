from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")


def contains_all(source: str, values: list[str]) -> bool:
    return all(value in source for value in values)


html_ids = re.findall(r'id="([^"]+)"', HTML)
checks = {
    "html_ids_are_unique": len(html_ids) == len(set(html_ids)),
    "three_top_level_routes": contains_all(
        HTML,
        ['data-route="learning"', 'data-route="exam"', 'data-route="qa"'],
    ),
    "learning_and_exam_hubs_exist": contains_all(
        HTML,
        ['id="learning-hub-page"', 'id="assessment-hub-page"'],
    ),
    "shared_module_gateway_exists": contains_all(
        HTML,
        ['id="module-gateway-page"', 'id="module-route-grid"', 'id="gateway-back"'],
    ),
    "four_activity_entries_exist": contains_all(
        HTML,
        [
            'data-route="learning/course"',
            'data-route="learning/practice"',
            'data-route="exam/objective"',
            'data-route="exam/simulation"',
        ],
    ),
    "hash_router_supports_activity_module": contains_all(
        JS,
        [
            "function routePath(",
            "function parseRouteHash(",
            "raw.startsWith(`${route}/`)",
            "exactModuleById(moduleId)",
            "window.addEventListener(\"hashchange\"",
            "window.addEventListener(\"popstate\"",
        ],
    ),
    "four_activity_routes_are_configured": contains_all(
        JS,
        [
            '"learning/course": {',
            '"learning/practice": {',
            '"exam/objective": {',
            '"exam/simulation": {',
        ],
    ),
    "objective_and_simulation_keep_independent_modules": contains_all(
        JS,
        [
            "objectiveModuleId",
            "simulationModuleId",
            'if (route === "exam/objective")',
            'if (route === "exam/simulation")',
        ],
    ),
    "objective_page_renders_only_objective_exam": contains_all(
        JS,
        [
            'if (state.route === "exam/objective") {',
            "els.testScenario.innerHTML = renderObjectiveExam();",
            "bindObjectiveExam(els.testScenario);",
        ],
    ) and bool(
        re.search(
            r'if \(state\.route === "exam/objective"\) \{.*?renderObjectiveExam\(\);.*?bindObjectiveExam\(els\.testScenario\);\s*return;',
            JS,
            re.S,
        )
    ),
    "conversation_is_hidden_on_objective_exam": (
        'const showConversation = state.route === "qa" || ((state.route === "learning/practice" || state.route === "exam/simulation") && workspace);'
        in JS
    ),
    "simulation_has_dedicated_customer_copy": contains_all(
        JS,
        [
            'if (state.route === "exam/simulation")',
            'kicker: "模拟顾客考核"',
            'conversation: "独立接待模拟顾客"',
            'finish: "完成考核并查看结果"',
        ],
    ),
    "user_facing_copy_avoids_layout_explanations": not any(
        phrase in f"{HTML}\n{JS}"
        for phrase in ["页面只展示当前任务需要的内容", "避免题目和对话内容同时堆叠"]
    ),
    "unified_typography_tokens_exist": contains_all(
        CSS,
        [
            "--font-caption: 12px",
            "--font-small: 13px",
            "--font-body: 15px",
            "--font-heading: 22px",
            "--font-page: clamp(32px, 3vw, 40px)",
        ],
    ),
    "responsive_layout_uses_mobile_and_tablet_breakpoints": contains_all(
        CSS,
        [
            "@media (max-width: 900px)",
            "@media (min-width: 640px) and (max-width: 900px)",
            ".module-route-grid { grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));",
        ],
    ),
    "static_asset_versions_are_synced": bool(
        re.search(r'styles\.css\?v=([^"\s]+)', HTML)
        and re.search(r'app\.js\?v=([^"\s]+)', HTML)
        and re.search(r'styles\.css\?v=([^"\s]+)', HTML).group(1)
        == re.search(r'app\.js\?v=([^"\s]+)', HTML).group(1)
    ),
    "default_route_is_simple_learning_hub": 'raw = LEGACY_ROUTES[raw] || raw || "learning";' in JS,
}

report = {
    "status": "passed" if all(checks.values()) else "failed",
    "checks": checks,
}
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "passed" else 1)
