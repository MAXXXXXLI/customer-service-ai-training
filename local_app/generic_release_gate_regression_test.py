from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOCAL_APP = ROOT / "local_app"
APP_JS = LOCAL_APP / "static" / "app.js"
sys.path.insert(0, str(LOCAL_APP))

import server  # noqa: E402


def scenario(scenario_id: str) -> dict[str, Any]:
    match = next((item for item in server.SCENARIOS if item.get("id") == scenario_id), None)
    assert match is not None, scenario_id
    return match


def opening_history(item: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": "assistant", "content": str(item.get("opening") or "")}]


def normalize(
    scenario_id: str,
    employee: str,
    candidate: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    item = scenario(scenario_id)
    return server.normalized_customer_reply(
        candidate,
        item,
        history or opening_history(item),
        employee,
    )


def test_all_scenario_rules_are_parseable_and_render_one_customer_turn() -> None:
    assert len(server.SCENARIOS) == 30
    for item in server.SCENARIOS:
        hidden = list(item.get("hidden_information") or [])
        rules = list(item.get("information_release_rules") or [])
        assert len(hidden) == 3, item.get("id")
        assert len(rules) == 3, item.get("id")
        for rule in rules:
            condition, disclosure = server.information_release_rule_parts(rule)
            rendered = server.information_release_reply(rule)
            assert condition and disclosure, {"scenario": item.get("id"), "rule": rule}
            if condition.startswith(("问", "询问", "追问")):
                core = re.sub(r"^(?:问|询问|追问)", "", condition).strip("“”\" '")
                assert (
                    core in server.GENERIC_RELEASE_QUESTION_PATTERNS
                    or core in server.GENERIC_RELEASE_SINGLE_QUESTION_PATTERNS
                ), {"scenario": item.get("id"), "condition": condition}
            else:
                assert condition in server.GENERIC_RELEASE_ACTION_PATTERNS, {
                    "scenario": item.get("id"),
                    "condition": condition,
                }
            assert rendered and len(rendered) <= 100, {"scenario": item.get("id"), "rule": rule, "reply": rendered}
            assert not server.customer_reply_is_invalid(rendered), rendered


def test_rule_bearing_scenario_blocks_hidden_facts_but_keeps_natural_grounded_text() -> None:
    item = scenario("SCN-CEX-M01-S02")
    history = opening_history(item)
    leaked = normalize(
        item["id"],
        "我先核对一下活动规则，再给您答复。",
        "我在成都门店，券下周到期，截图上的券名也看不清。",
        history,
    )
    assert "成都" not in leaked and "下周到期" not in leaked and "券名" not in leaked, leaked

    ordinary = normalize(
        item["id"],
        "我先核对一下活动规则，再给您答复。",
        "好，那你核对清楚以后再告诉我。",
        history,
    )
    assert ordinary == "好，那你核对清楚以后再告诉我。", ordinary


def test_semantic_paraphrase_cannot_bypass_an_untriggered_gate() -> None:
    leaked = normalize(
        "SCN-CEX-M03-S01",
        "我先核对一下情况。",
        "昨夜才开始疼，今早更厉害，胳膊木木的。",
    )
    assert not re.search(r"昨夜|今早|胳膊|木木", leaked), leaked


def test_every_rule_bearing_scenario_rejects_repeated_opening() -> None:
    for item in server.SCENARIOS:
        marker = item["opening"]
        result = server.normalized_customer_reply(
            marker,
            item,
            opening_history(item),
            "我先听您说完，再核对已知情况。",
        )
        assert result and result != marker, {"scenario": item["id"], "reply": result}


def test_negated_question_does_not_release_a_rule() -> None:
    denied = normalize(
        "SCN-CEX-M01-S01",
        "我不是在问您持续多久。",
        "已经两个月了。",
    )
    assert "两个月" not in denied, denied


def test_no_rule_scenario_still_preserves_safe_natural_model_text() -> None:
    base = scenario("SCN-CEX-M03-S02")
    without_rules = {
        **base,
        "id": "SCN-NO-RELEASE-RULES",
        "hidden_information": [],
        "information_release_rules": [],
    }
    natural = "大概有半年了，低头久了会更明显。"
    result = server.normalized_customer_reply(
        natural,
        without_rules,
        opening_history(without_rules),
        "这种情况多久了？",
    )
    assert result == natural, result


def test_one_turn_unlocks_at_most_one_group_and_later_turn_can_unlock_next() -> None:
    item = scenario("SCN-CEX-M01-S01")
    employee = "您的肩颈不舒服持续多久了？还有没有其他伴随症状？"
    first = normalize(item["id"], employee, "两个月了，而且偶尔手指发麻。")
    assert "两个月" in first, first
    assert "手指" not in first and "麻" not in first, first

    history = [
        *opening_history(item),
        {"role": "user", "content": employee},
        {"role": "assistant", "content": first},
    ]
    second = normalize(item["id"], employee, "两个月了，而且偶尔手指发麻。", history)
    assert "手指" in second or "麻" in second, second
    assert "两个月" not in second, second


def test_rule_release_does_not_depend_on_hidden_array_position() -> None:
    duration = normalize(
        "SCN-CEX-M06-S02",
        "这些症状已经持续几个小时了？",
        "已经六小时了，而且我喝不下水。",
    )
    assert "六小时" in duration and "水" not in duration, duration

    medicine = normalize(
        "SCN-CEX-M05-S03",
        "您目前有没有服用什么药物？",
        "我在服用甲状腺药，每天工作十小时也没运动。",
    )
    assert "甲状腺" in medicine and "十小时" not in medicine and "运动" not in medicine, medicine


def test_action_rules_require_an_affirmative_current_turn() -> None:
    item = scenario("SCN-CEX-M08-S03")
    released = normalize(
        item["id"],
        "没关系，我们今天马上做。",
        "我三天后还要去海边。",
    )
    assert "三天后" in released and "海边" in released, released

    denied = normalize(
        item["id"],
        "您现在有晒伤，所以今天不能马上做。",
        "我三天后还要去海边。",
    )
    assert "三天后" not in denied and "海边" not in denied, denied


def test_point_wave_specialized_release_order_is_unchanged() -> None:
    item = scenario("SCN-CEX-M03-S01")
    both = normalize(
        item["id"],
        "疼痛从什么时候开始、今天是否更重？还有没有手麻或无力？",
        "昨晚开始，今天更重，手臂也新发麻木。",
    )
    assert both == server.information_release_reply(item["information_release_rules"][0]), both

    companion = normalize(
        item["id"],
        "还有没有手麻、无力或其他伴随症状？",
        "昨晚开始，今天更重，手臂也新发麻木。",
    )
    assert companion == server.information_release_reply(item["information_release_rules"][1]), companion


def test_point_wave_in_session_reply_tracks_the_employee_action_across_turns() -> None:
    item = scenario("SCN-CEX-M03-S02")
    opening = opening_history(item)
    combined_employee = (
        "是的，辛苦您忍几分钟。如果您实在很痛，"
        "我可以先帮您把力度调低一些。"
    )
    lowered = normalize(item["id"], combined_employee, "模型输出了无关的服务后酸痛回答。", opening)
    assert lowered == "我已经很痛了，能不能先停下来？", lowered

    continued = normalize(
        item["id"],
        "辛苦您再忍一会儿试试。",
        "模型输出了另一个无关回答。",
        opening,
    )
    assert continued == "我已经很痛了，能不能先停下来？", continued

    lower_history = [
        *opening,
        {"role": "user", "content": combined_employee},
        {"role": "assistant", "content": lowered},
    ]
    pain_score = normalize(
        item["id"],
        "现在疼痛大概是几分？",
        "模型提前泄露了多条隐藏信息。",
        lower_history,
    )
    assert pain_score == "大概8分。", pain_score

    pain_feeling = normalize(
        item["id"],
        "我先暂停一下。现在是酸胀、刺痛，还是像电到一样？",
        "我现在主要还是想尽快处理，其他专业的我也不太懂。",
        [*lower_history, {"role": "user", "content": "现在疼痛大概是几分？"}, {"role": "assistant", "content": pain_score}],
    )
    assert pain_feeling == "像电到一样。", pain_feeling

    companion = normalize(
        item["id"],
        "收到，8分属于明显疼痛，我们今天不再继续操作。现在有没有麻木、无力、明显肿胀、发热，或者疼痛还在加重？",
        "我比较怕疼，过程中会不会很难受？",
        [*lower_history, {"role": "user", "content": "现在疼痛大概是几分？"}, {"role": "assistant", "content": pain_score}],
    )
    assert "没有麻木" in companion and "没有继续加重" in companion, companion

    safe_closure = normalize(
        item["id"],
        "我们已经停止今天的操作。我会记录本次部位、能量和反应，并请负责人马上复核；如果持续加重，建议尽快由医疗机构评估。",
        "我现在主要还是想尽快处理，其他专业的我也不太懂。",
        opening,
    )
    assert "今天就先不做" in safe_closure and "负责人" in safe_closure, safe_closure

    denied = normalize(
        item["id"],
        "您不用忍，我们先暂停，也不降低能量继续做。",
        "好的那我再忍一会儿试试",
        opening,
    )
    assert denied != "我已经很痛了，能不能先停下来？", denied


def run_static_cases(cases: list[dict[str, Any]]) -> list[str]:
    node = shutil.which("node") or str(
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
    )
    script = r'''
const fs = require("fs");
const noop = () => {};
const element = new Proxy({
  value: "", dataset: {}, style: {},
  classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
  addEventListener: noop, querySelectorAll: () => [], querySelector: () => null,
}, { get: (target, key) => key in target ? target[key] : noop, set: (target, key, value) => (target[key] = value, true) });
global.localStorage = { getItem: () => "", setItem: noop, removeItem: noop };
global.document = { getElementById: () => element, querySelectorAll: () => [], querySelector: () => null, createElement: () => element, body: element };
global.window = { addEventListener: noop, location: { hostname: "example.test", pathname: "/", hash: "" } };
global.location = window.location;
global.history = { pushState: noop, replaceState: noop };
global.navigator = {};
const source = fs.readFileSync(process.argv[1], "utf8");
const prefix = source.slice(0, source.indexOf("async function boot()"));
eval(prefix + "\nglobalThis.__normalizeGate = normalizeStaticCustomerReply;");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const cases = JSON.parse(input);
  const output = cases.map((item) => __normalizeGate(item.candidate, item.scenario, item.history, item.employee));
  process.stdout.write(JSON.stringify(output));
});
'''
    completed = subprocess.run(
        [node, "-e", script, str(APP_JS)],
        input=json.dumps(cases, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def test_static_and_server_gates_match_representative_cases() -> None:
    definitions = [
        ("SCN-CEX-M01-S01", "持续多久？有没有其他伴随症状？", "两个月，偶尔手指发麻。"),
        ("SCN-CEX-M01-S02", "我先核对活动规则再答复。", "我在成都，券下周到期。"),
        ("SCN-CEX-M06-S02", "这些症状持续几个小时了？", "六小时了，而且喝不下水。"),
        ("SCN-CEX-M09-S01", "您现在最在意哪个部位，目标是什么？", "口周和下颌缘，太阳穴也凹。"),
        ("SCN-CEX-M03-S01", "什么时候开始，今天有没有更重？", "昨晚开始，今天更重，手臂也麻了。"),
        ("SCN-CEX-M03-S01", "我先核对一下情况。", "昨夜才开始疼，今早更厉害，胳膊木木的。"),
        ("SCN-CEX-M03-S02", "如果实在很痛，我可以把力度调低一些。", "无关回复。"),
        ("SCN-CEX-M03-S02", "辛苦您再忍一会儿试试。", "无关回复。"),
        ("SCN-CEX-M03-S02", "我先暂停一下。现在是酸胀、刺痛，还是像电到一样？", "无关回复。"),
        ("SCN-CEX-M03-S02", "收到，8分属于明显疼痛，我们今天不再继续操作。现在有没有麻木、无力、明显肿胀、发热，或者疼痛还在加重？", "无关回复。"),
        ("SCN-CEX-M03-S02", "我们已经停止今天的操作。我会记录本次部位、能量和反应，并请负责人马上复核；如果持续加重，建议尽快由医疗机构评估。", "无关回复。"),
        ("SCN-CEX-M01-S01", "我不是在问您持续多久。", "已经两个月了。"),
    ]
    cases = []
    server_output = []
    for scenario_id, employee, candidate in definitions:
        item = scenario(scenario_id)
        history = opening_history(item)
        cases.append({"scenario": item, "history": history, "employee": employee, "candidate": candidate})
        server_output.append(server.normalized_customer_reply(candidate, item, history, employee))
    for item in server.SCENARIOS:
        marker = f"前后端同构原始回复-{item['id']}"
        employee = "我先听您说完，再核对已知情况。"
        history = opening_history(item)
        cases.append({"scenario": item, "history": history, "employee": employee, "candidate": marker})
        server_output.append(server.normalized_customer_reply(marker, item, history, employee))
    static_output = run_static_cases(cases)
    assert static_output == server_output, {"server": server_output, "static": static_output}


if __name__ == "__main__":
    tests = [
        test_all_scenario_rules_are_parseable_and_render_one_customer_turn,
        test_rule_bearing_scenario_blocks_hidden_facts_but_keeps_natural_grounded_text,
        test_semantic_paraphrase_cannot_bypass_an_untriggered_gate,
        test_every_rule_bearing_scenario_rejects_repeated_opening,
        test_negated_question_does_not_release_a_rule,
        test_no_rule_scenario_still_preserves_safe_natural_model_text,
        test_one_turn_unlocks_at_most_one_group_and_later_turn_can_unlock_next,
        test_rule_release_does_not_depend_on_hidden_array_position,
        test_action_rules_require_an_affirmative_current_turn,
        test_point_wave_specialized_release_order_is_unchanged,
        test_point_wave_in_session_reply_tracks_the_employee_action_across_turns,
        test_static_and_server_gates_match_representative_cases,
    ]
    passed = []
    for test in tests:
        test()
        passed.append(test.__name__)
    print(json.dumps({"status": "passed", "tests": passed}, ensure_ascii=False))
