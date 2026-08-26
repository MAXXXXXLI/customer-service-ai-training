from __future__ import annotations

import json
import os

import server


def live_turn(api_key: str, payload: dict) -> dict:
    result = server.handle_chat({**payload, "api_key": api_key})
    assert result.get("ok") is True, result
    assert result.get("meta", {}).get("mock") is False, result.get("meta")
    return result


def main() -> None:
    api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("请先通过 SILICONFLOW_API_KEY 环境变量提供真实 API 密钥。")

    aftercare = next(item for item in server.SCENARIOS if item.get("id") == "SCN-CEX-M03-S01")
    aftercare_history = [{"role": "assistant", "content": aftercare["opening"]}]
    aftercare_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": aftercare["id"],
        "history": aftercare_history,
        "message": server.POINT_WAVE_BEST_REPLY,
    })
    assert aftercare_result["result"]["feedback"]["level"] == "good", aftercare_result["result"]
    assert aftercare_result["result"]["feedback"]["suggested_reply"] == server.POINT_WAVE_BEST_REPLY

    in_session = next(item for item in server.SCENARIOS if item.get("id") == "SCN-CEX-M03-S02")
    opening_history = [{"role": "assistant", "content": in_session["opening"]}]
    lower_employee = (
        "是的，辛苦您忍几分钟。如果您实在很痛，"
        "我可以先帮您把力度调低一些。"
    )
    lower_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": opening_history,
        "message": lower_employee,
    })
    assert lower_result["result"]["customer_reply"] == "好的那把能量调低一些", lower_result["result"]

    continued_history = [
        *opening_history,
        {"role": "user", "content": lower_employee},
        {"role": "assistant", "content": lower_result["result"]["customer_reply"]},
    ]
    pain_score_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": continued_history,
        "message": "现在疼痛大概是几分？",
    })
    assert pain_score_result["result"]["customer_reply"] == "大概8分。", pain_score_result["result"]

    pain_history = [
        *continued_history,
        {"role": "user", "content": "现在疼痛大概是几分？"},
        {"role": "assistant", "content": pain_score_result["result"]["customer_reply"]},
    ]
    feeling_employee = "我先暂停一下。现在是酸胀、刺痛，还是像电到一样？"
    feeling_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": pain_history,
        "message": feeling_employee,
    })
    assert feeling_result["result"]["customer_reply"] == "像电到一样。", feeling_result["result"]
    assert feeling_result["result"]["feedback"]["level"] == "good", feeling_result["result"]

    companion_employee = "收到，8分属于明显疼痛，我们今天不再继续操作。现在有没有麻木、无力、明显肿胀、发热，或者疼痛还在加重？"
    companion_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": pain_history,
        "message": companion_employee,
    })
    companion_reply = companion_result["result"]["customer_reply"]
    assert "没有麻木" in companion_reply and "没有继续加重" in companion_reply, companion_result["result"]
    assert companion_result["result"]["feedback"]["level"] == "good", companion_result["result"]

    closure_history = [
        *pain_history,
        {"role": "user", "content": companion_employee},
        {"role": "assistant", "content": companion_reply},
    ]
    closure_employee = "我们已经停止今天的操作。我会记录本次部位、能量和反应，并请负责人马上复核；如果持续加重，建议尽快由医疗机构评估。"
    closure_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": closure_history,
        "message": closure_employee,
    })
    assert closure_result["result"]["customer_reply"].startswith("好，那今天就先不做了"), closure_result["result"]
    assert closure_result["result"]["feedback"]["level"] == "good", closure_result["result"]
    assert "过程中会不会很难受" not in closure_result["result"]["feedback"]["issue"], closure_result["result"]

    endure_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": opening_history,
        "message": "辛苦您再忍一会儿试试。",
    })
    assert endure_result["result"]["customer_reply"] == "好的那我再忍一会儿试试", endure_result["result"]

    results = [aftercare_result, lower_result, pain_score_result, feeling_result, companion_result, closure_result, endure_result]
    summary = {
        "status": "passed",
        "provider": "SiliconFlow",
        "model": aftercare_result["meta"].get("model"),
        "all_requests_used_real_api": all(not item["meta"].get("mock") for item in results),
        "all_roles_returned_without_fallback": all(not item["meta"].get("degraded") for item in results),
        "fallback_roles": [item["meta"].get("fallback_roles", []) for item in results],
        "service_aftercare": {
            "feedback": aftercare_result["result"]["feedback"]["level"],
            "exact_best_reply": True,
        },
        "in_session_lower_energy": lower_result["result"]["customer_reply"],
        "continuous_next_turn": pain_score_result["result"]["customer_reply"],
        "continuous_feeling": feeling_result["result"]["customer_reply"],
        "continuous_companion": companion_reply,
        "continuous_closure": closure_result["result"]["customer_reply"],
        "coach_role_attribution_grounded": "过程中会不会很难受" not in closure_result["result"]["feedback"]["issue"],
        "in_session_endure": endure_result["result"]["customer_reply"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
