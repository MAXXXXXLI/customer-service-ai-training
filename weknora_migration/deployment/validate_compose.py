#!/usr/bin/env python3
"""Validate resolved Compose configuration and live WeKnora containers.

The program deliberately emits only field names on failure. It never prints
resolved environment values because the JSON input contains deployment secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_IMAGES = {
    "frontend": "wechatopenai/weknora-ui:v0.7.2@sha256:b1993a70eec0d1879461a3fbba5d24c021adebdc850807938c20a9760628caa5",
    "app": "wechatopenai/weknora-app:v0.7.2@sha256:7cb9d5f25f626f82ec4b2369295313c5df0108757d28f4f18ada29337060025f",
    "docreader": "wechatopenai/weknora-docreader:v0.7.2@sha256:b9c4636b65b5d4947d5e09cd311ba6cf37f1f2da37c51d4be2b911d432f12abe",
    "postgres": "paradedb/paradedb:v0.22.2-pg17@sha256:af585013f97f622715de01e48d00558f7edf17055d7b40deafc9f98ca8d99a56",
    "redis": "redis:7.0-alpine@sha256:c9d92d840fd011c908f040592857c724ae6d877f2aba5c40ad963276507386b2",
}

EXPECTED_CONTAINERS = {
    "frontend": "WeKnora-frontend",
    "app": "WeKnora-app",
    "docreader": "WeKnora-docreader",
    "postgres": "WeKnora-postgres",
    "redis": "WeKnora-redis",
}

EXPECTED_PORTS = {
    "frontend": {("127.0.0.1", "18080", "80", "tcp")},
    "app": {("127.0.0.1", "18081", "8080", "tcp")},
    "docreader": set(),
    "postgres": set(),
    "redis": set(),
}


def fail(message: str) -> None:
    raise SystemExit(f"deployment assertion failed: {message}")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in raw_line:
            fail(f"invalid .env syntax at line {number}")
        key, value = raw_line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            fail(f"invalid .env key at line {number}")
        if key in values:
            fail(f"duplicate .env key: {key}")
        values[key] = value
    return values


def environment_map(service: dict[str, Any]) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return {str(key): "" if value is None else str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result: dict[str, str] = {}
        for item in raw:
            key, separator, value = str(item).partition("=")
            result[key] = value if separator else ""
        return result
    fail("resolved service environment has an unexpected type")
    return {}


def required_env(env: dict[str, str], key: str) -> str:
    if key not in env:
        fail(f"required .env key is missing: {key}")
    return env[key]


def assert_environment_value(
    service_name: str, service: dict[str, Any], key: str, expected: str
) -> None:
    if environment_map(service).get(key) != expected:
        fail(f"{service_name} environment mismatch for {key}")


def command_contains_value(service: dict[str, Any], value: str) -> bool:
    command = service.get("command")
    if command is None:
        command = service.get("Cmd")
    if isinstance(command, list):
        return any(value == str(item) or value in str(item).split() for item in command)
    return value in str(command or "").split()


def resolved_ports(service: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    result: set[tuple[str, str, str, str]] = set()
    for port in service.get("ports") or []:
        if not isinstance(port, dict):
            fail("Compose did not canonicalize a port mapping")
        result.add(
            (
                str(port.get("host_ip") or ""),
                str(port.get("published") or ""),
                str(port.get("target") or ""),
                str(port.get("protocol") or "tcp"),
            )
        )
    return result


def image_identity(reference: str) -> tuple[str, str]:
    if "@sha256:" not in reference:
        fail("image reference is not digest-pinned")
    name, digest = reference.rsplit("@", 1)
    name = name.removeprefix("index.docker.io/")
    name = name.removeprefix("docker.io/")
    name = name.removeprefix("library/")
    slash = name.rfind("/")
    colon = name.rfind(":")
    if colon > slash:
        name = name[:colon]
    return name, digest


def validate_config(payload: Any, env: dict[str, str], registration: str) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("services"), dict):
        fail("invalid Compose config JSON")
    services: dict[str, dict[str, Any]] = payload["services"]
    missing = set(EXPECTED_IMAGES) - set(services)
    if missing:
        fail("missing required services: " + ", ".join(sorted(missing)))

    default_services = {
        name for name, service in services.items() if not service.get("profiles")
    }
    if default_services != set(EXPECTED_IMAGES):
        fail("default Compose profile is not exactly the five approved services")

    for service_name, expected_image in EXPECTED_IMAGES.items():
        if image_identity(str(services[service_name].get("image") or "")) != image_identity(
            expected_image
        ):
            fail(f"resolved image mismatch for {service_name}")
        if resolved_ports(services[service_name]) != EXPECTED_PORTS[service_name]:
            fail(f"resolved host port mismatch for {service_name}")

    app = services["app"]
    for key in (
        "DB_PASSWORD",
        "REDIS_PASSWORD",
        "JWT_SECRET",
        "SYSTEM_AES_KEY",
        "GRPC_AUTH_TOKEN",
        "WEKNORA_TENANT_ENABLE_RBAC",
        "WEKNORA_TENANT_ENABLE_CROSS_TENANT_ACCESS",
        "WEKNORA_SANDBOX_MODE",
    ):
        assert_environment_value("app", app, key, required_env(env, key))
    assert_environment_value("app", app, "DISABLE_REGISTRATION", registration)
    assert_environment_value("app", app, "OIDC_AUTH_ENABLE", "false")
    assert_environment_value(
        "app",
        app,
        "WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL",
        required_env(env, "WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL"),
    )
    assert_environment_value(
        "docreader",
        services["docreader"],
        "GRPC_AUTH_TOKEN",
        required_env(env, "GRPC_AUTH_TOKEN"),
    )
    assert_environment_value(
        "postgres",
        services["postgres"],
        "POSTGRES_PASSWORD",
        required_env(env, "DB_PASSWORD"),
    )
    assert_environment_value(
        "postgres", services["postgres"], "POSTGRES_USER", required_env(env, "DB_USER")
    )
    assert_environment_value(
        "postgres", services["postgres"], "POSTGRES_DB", required_env(env, "DB_NAME")
    )
    assert_environment_value(
        "frontend", services["frontend"], "APP_HOST", required_env(env, "APP_HOST")
    )
    assert_environment_value(
        "frontend",
        services["frontend"],
        "APP_PORT",
        required_env(env, "APP_BACKEND_PORT"),
    )
    if not command_contains_value(services["redis"], required_env(env, "REDIS_PASSWORD")):
        fail("resolved redis command does not use REDIS_PASSWORD")


def runtime_ports(container: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    result: set[tuple[str, str, str, str]] = set()
    ports = container.get("NetworkSettings", {}).get("Ports") or {}
    for target_protocol, bindings in ports.items():
        if not bindings:
            continue
        target, _, protocol = target_protocol.partition("/")
        for binding in bindings:
            result.add(
                (
                    str(binding.get("HostIp") or ""),
                    str(binding.get("HostPort") or ""),
                    target,
                    protocol or "tcp",
                )
            )
    return result


def runtime_environment(container: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in container.get("Config", {}).get("Env") or []:
        key, separator, value = str(item).partition("=")
        result[key] = value if separator else ""
    return result


def validate_runtime(
    payload: Any, env: dict[str, str], registration: str, project: str
) -> None:
    if not isinstance(payload, list):
        fail("invalid docker inspect JSON")
    by_service: dict[str, dict[str, Any]] = {}
    for container in payload:
        labels = container.get("Config", {}).get("Labels") or {}
        if labels.get("com.docker.compose.project") != project:
            fail("runtime container belongs to an unexpected Compose project")
        service = labels.get("com.docker.compose.service")
        if service in by_service:
            fail(f"multiple runtime containers found for {service}")
        by_service[str(service)] = container

    if set(by_service) != set(EXPECTED_IMAGES):
        fail("runtime service set is not exactly the five approved services")

    for service_name, expected_name in EXPECTED_CONTAINERS.items():
        container = by_service[service_name]
        if str(container.get("Name", "")).lstrip("/") != expected_name:
            fail(f"runtime container name mismatch for {service_name}")
        state = container.get("State") or {}
        if (
            state.get("Running") is not True
            or state.get("Status") != "running"
            or state.get("Restarting") is True
        ):
            fail(f"runtime service is not running: {service_name}")
        if service_name in {"app", "docreader", "postgres"}:
            if (state.get("Health") or {}).get("Status") != "healthy":
                fail(f"runtime service is not healthy: {service_name}")
        if runtime_ports(container) != EXPECTED_PORTS[service_name]:
            fail(f"runtime host port mismatch for {service_name}")
        if container.get("HostConfig", {}).get("NetworkMode") == "host":
            fail(f"host network mode is forbidden for {service_name}")
        if container.get("HostConfig", {}).get("Privileged") is True:
            fail(f"privileged mode is forbidden for {service_name}")

        actual_image = str(container.get("Config", {}).get("Image") or "")
        if image_identity(actual_image) != image_identity(EXPECTED_IMAGES[service_name]):
            fail(f"runtime image mismatch for {service_name}")

    app_environment = runtime_environment(by_service["app"])
    for key in (
        "DB_PASSWORD",
        "REDIS_PASSWORD",
        "JWT_SECRET",
        "SYSTEM_AES_KEY",
        "GRPC_AUTH_TOKEN",
        "WEKNORA_TENANT_ENABLE_RBAC",
        "WEKNORA_TENANT_ENABLE_CROSS_TENANT_ACCESS",
        "WEKNORA_SANDBOX_MODE",
    ):
        if app_environment.get(key) != required_env(env, key):
            fail(f"runtime app environment mismatch for {key}")
    if app_environment.get("DISABLE_REGISTRATION") != registration:
        fail("runtime app environment mismatch for DISABLE_REGISTRATION")
    if app_environment.get("OIDC_AUTH_ENABLE") != "false":
        fail("runtime app environment mismatch for OIDC_AUTH_ENABLE")
    if app_environment.get("WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL") != required_env(
        env, "WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL"
    ):
        fail("runtime app environment mismatch for WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL")
    if runtime_environment(by_service["docreader"]).get(
        "GRPC_AUTH_TOKEN"
    ) != required_env(env, "GRPC_AUTH_TOKEN"):
        fail("runtime docreader environment mismatch for GRPC_AUTH_TOKEN")
    postgres_environment = runtime_environment(by_service["postgres"])
    if postgres_environment.get("POSTGRES_PASSWORD") != required_env(env, "DB_PASSWORD"):
        fail("runtime postgres environment mismatch for POSTGRES_PASSWORD")
    if postgres_environment.get("POSTGRES_USER") != required_env(env, "DB_USER"):
        fail("runtime postgres environment mismatch for POSTGRES_USER")
    if postgres_environment.get("POSTGRES_DB") != required_env(env, "DB_NAME"):
        fail("runtime postgres environment mismatch for POSTGRES_DB")
    frontend_environment = runtime_environment(by_service["frontend"])
    if frontend_environment.get("APP_HOST") != required_env(env, "APP_HOST"):
        fail("runtime frontend environment mismatch for APP_HOST")
    if frontend_environment.get("APP_PORT") != required_env(env, "APP_BACKEND_PORT"):
        fail("runtime frontend environment mismatch for APP_PORT")
    if not command_contains_value(
        by_service["redis"].get("Config") or {}, required_env(env, "REDIS_PASSWORD")
    ):
        fail("runtime redis command does not use REDIS_PASSWORD")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("config", "runtime"))
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--registration", required=True, choices=("true", "false"))
    parser.add_argument("--project")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = read_env(args.env_file)
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        fail(f"invalid JSON input: {exc}")

    if args.mode == "config":
        validate_config(payload, env, args.registration)
    else:
        if not args.project:
            fail("runtime validation requires --project")
        validate_runtime(payload, env, args.registration, args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
