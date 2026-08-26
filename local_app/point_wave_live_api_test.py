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

    endure_result = live_turn(api_key, {
        "mode": "training",
        "scenario_id": in_session["id"],
        "history": opening_history,
        "message": "辛苦您再忍一会儿试试。",
    })
    assert endure_result["result"]["customer_reply"] == "好的那我再忍一会儿试试", endure_result["result"]

    results = [aftercare_result, lower_result, pain_score_result, endure_result]
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
        "in_session_endure": endure_result["result"]["customer_reply"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
