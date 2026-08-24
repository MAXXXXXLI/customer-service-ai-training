from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import server


ROOT = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT / "local_app" / "static" / "app.js"
SCENARIO_ID = "SCN-CEX-M01-S01"
EMPLOYEE_MESSAGE = "我了解您不想听一堆项目。我先只围绕肩颈这件事说清楚，可以吗？"


def training_payload() -> dict[str, Any]:
    scenario = next(item for item in server.SCENARIOS if item.get("id") == SCENARIO_ID)
    return {
        "mode": "training",
        "action": "turn",
        "scenario_id": SCENARIO_ID,
        "message": EMPLOYEE_MESSAGE,
        "history": [{"role": "assistant", "content": scenario["opening"]}],
        "api_key": "sk-regression-placeholder",
    }


def model_feedback(issue: str) -> str:
    return json.dumps({
        "feedback": {
            "level": "good",
            "issue": issue,
            "why": "这句话承接了顾客的当前问题。",
            "method_step": "承接问题并补充必要询问",
            "knowledge_focus": "顾客已表达的需求",
            "suggested_reply": "我理解您想先听重点，肩颈不舒服大概多久了？",
            "next_goal": "根据顾客的回答继续了解影响。",
        }
    }, ensure_ascii=False)


def run_with_model(
    fake_call: Callable[..., tuple[str, dict[str, Any]]],
    *,
    wait_seconds: float | None = None,
) -> dict[str, Any]:
    original_call = server.call_model
    original_mock_mode = server.MOCK_MODE
    original_wait_seconds = server.TRAINING_DUAL_CALL_WAIT_SECONDS
    server.call_model = fake_call
    server.MOCK_MODE = False
    if wait_seconds is not None:
        server.TRAINING_DUAL_CALL_WAIT_SECONDS = wait_seconds
    try:
        return server.handle_chat(training_payload())
    finally:
        server.call_model = original_call
        server.MOCK_MODE = original_mock_mode
        server.TRAINING_DUAL_CALL_WAIT_SECONDS = original_wait_seconds


def is_customer_system(system: str) -> bool:
    # Editable preferences are intentionally placed before the fixed prompt;
    # identify the role by the protected long prompt rather than its prefix.
    return server.TRAIN_CUSTOMER_SYSTEM in system


def test_customer_failure_keeps_real_coach_and_uses_customer_fallback() -> None:
    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if is_customer_system(system):
            raise RuntimeError("customer unavailable")
        time.sleep(0.05)
        return model_feedback("真实教练结果已保留"), {"model": "coach-model", "usage": {"total_tokens": 17}}

    response = run_with_model(fake_call)
    assert response["result"]["customer_reply"], response
    assert response["result"]["feedback"]["issue"] == "真实教练结果已保留", response
    assert response["meta"]["degraded"] is True, response
    assert response["meta"]["fallback_roles"] == ["customer"], response
    assert response["meta"]["usage"]["total_tokens"] == 17, response


def test_early_failure_preserves_healthy_peer_finishing_after_one_second() -> None:
    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if is_customer_system(system):
            raise RuntimeError("customer unavailable")
        time.sleep(1.2)
        return model_feedback("1.2 秒后返回的真实教练结果已保留"), {
            "model": "coach-model",
            "usage": {"total_tokens": 19},
        }

    started = time.monotonic()
    response = run_with_model(fake_call, wait_seconds=2.5)
    elapsed = time.monotonic() - started

    assert 1.0 <= elapsed < 2.5, f"未在共享预算内等待健康 peer: {elapsed:.2f}s"
    assert response["result"]["feedback"]["issue"] == "1.2 秒后返回的真实教练结果已保留", response
    assert response["meta"]["fallback_roles"] == ["customer"], response
    assert response["meta"]["usage"]["total_tokens"] == 19, response


def test_coach_failure_keeps_real_customer_and_uses_local_feedback() -> None:
    customer_reply = "好，那就先只说肩颈这一件事。"

    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if is_customer_system(system):
            time.sleep(0.05)
            return json.dumps({"customer_reply": customer_reply}, ensure_ascii=False), {"model": "customer-model", "usage": {"total_tokens": 11}}
        raise RuntimeError("coach unavailable")

    response = run_with_model(fake_call)
    payload = training_payload()
    scenario = next(item for item in server.SCENARIOS if item.get("id") == SCENARIO_ID)
    expected_reply = server.normalized_customer_reply(
        customer_reply, scenario, payload["history"], EMPLOYEE_MESSAGE,
    )
    assert expected_reply != customer_reply, "带释放规则的场景不应原样直通模型顾客句"
    assert response["result"]["customer_reply"] == expected_reply, response
    feedback = response["result"]["feedback"]
    assert feedback["issue"] == "你有继续追问顾客目标，方向正确。", response
    assert all(feedback.get(key) for key in (
        "level", "issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal",
    )), response
    assert response["meta"]["degraded"] is True, response
    assert response["meta"]["fallback_roles"] == ["feedback"], response
    assert response["meta"]["usage"]["total_tokens"] == 11, response


def test_both_failures_are_explicit() -> None:
    barrier = threading.Barrier(2)

    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        barrier.wait(timeout=1)
        role = "customer" if is_customer_system(system) else "coach"
        raise RuntimeError(f"{role} unavailable")

    try:
        run_with_model(fake_call)
    except RuntimeError as exc:
        assert "模拟顾客与训练教练均未返回可用结果" in str(exc), exc
    else:
        raise AssertionError("两路均失败时未返回明确错误")


def test_early_failure_does_not_wait_for_peer_timeout() -> None:
    release_peer = threading.Event()

    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if is_customer_system(system):
            raise RuntimeError("customer failed immediately")
        release_peer.wait(5)
        return model_feedback("这个结果不应被等待"), {"model": "slow-coach", "usage": {}}

    started = time.monotonic()
    try:
        run_with_model(fake_call, wait_seconds=0.15)
    except RuntimeError as exc:
        assert "均未返回可用结果" in str(exc), exc
    else:
        raise AssertionError("挂起的另一路不应阻塞当前请求")
    finally:
        elapsed = time.monotonic() - started
        release_peer.set()
    assert elapsed < 0.8, f"单路早期失败后超出总等待预算 {elapsed:.2f}s"


def test_successful_role_does_not_wait_for_hanging_peer_provider_timeout() -> None:
    release_peer = threading.Event()
    customer_reply = "好，那就先只说肩颈这一件事。"

    def fake_call(system: str, *_args: Any, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
        if is_customer_system(system):
            return json.dumps({"customer_reply": customer_reply}, ensure_ascii=False), {
                "model": "customer-model",
                "usage": {"total_tokens": 13},
            }
        release_peer.wait(5)
        return model_feedback("超时后的结果不应被接纳"), {"model": "slow-coach", "usage": {}}

    started = time.monotonic()
    try:
        response = run_with_model(fake_call, wait_seconds=0.15)
    finally:
        elapsed = time.monotonic() - started
        release_peer.set()

    assert elapsed < 0.8, f"已成功的角色仍被挂起 peer 阻塞 {elapsed:.2f}s"
    payload = training_payload()
    scenario = next(item for item in server.SCENARIOS if item.get("id") == SCENARIO_ID)
    expected_reply = server.normalized_customer_reply(
        customer_reply, scenario, payload["history"], EMPLOYEE_MESSAGE,
    )
    assert expected_reply != customer_reply, "带释放规则的场景不应原样直通模型顾客句"
    assert response["result"]["customer_reply"] == expected_reply, response
    assert response["result"]["feedback"]["issue"] == "你有继续追问顾客目标，方向正确。", response
    assert response["meta"]["degraded"] is True, response
    assert response["meta"]["fallback_roles"] == ["feedback"], response
    assert response["meta"]["usage"]["total_tokens"] == 13, response


def test_static_training_uses_role_specific_all_settled_fallbacks() -> None:
    source = APP_JS_PATH.read_text(encoding="utf-8")
    training_start = source.index('if (mode === "training") {', source.index("async function staticApi"))
    training_end = source.index("\n  let system;", training_start)
    block = source[training_start:training_end]
    assert "Promise.allSettled([" in block, "静态训练未使用 allSettled"
    assert 'customerSettled.status === "fulfilled"' in block
    assert 'coachSettled.status === "fulfilled"' in block
    assert 'customer_reply: localFallback.customer_reply' in block
    assert 'feedback: localFallback.feedback' in block
    assert "if (!customerModelResult && !coachModelResult)" in block
    assert 'fallback_roles:' in block
    assert "Promise.all([" not in block


TESTS = [
    test_customer_failure_keeps_real_coach_and_uses_customer_fallback,
    test_early_failure_preserves_healthy_peer_finishing_after_one_second,
    test_coach_failure_keeps_real_customer_and_uses_local_feedback,
    test_both_failures_are_explicit,
    test_early_failure_does_not_wait_for_peer_timeout,
    test_successful_role_does_not_wait_for_hanging_peer_provider_timeout,
    test_static_training_uses_role_specific_all_settled_fallbacks,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(TESTS)} dual-call resilience regressions passed.")
