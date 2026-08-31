#!/usr/bin/env bash

# Shared, fail-closed helpers for the pinned WeKnora v0.7.2 deployment.
# Callers must enable `set -euo pipefail` before sourcing this file.

WEKNORA_COMPOSE_PROJECT=weknora-v072
WEKNORA_DEPLOYMENT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

WEKNORA_CONTAINER_NAMES=(
  WeKnora-frontend
  WeKnora-app
  WeKnora-docreader
  WeKnora-postgres
  WeKnora-redis
)

weknora_env_value() {
  local target=$1
  local name=$2
  awk -F= -v wanted="$name" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$target/.env"
}

weknora_validate_env_file() {
  local target=$1
  local env_file="$target/.env"
  local mode

  [[ -f $env_file && ! -L $env_file ]] || {
    echo ".env must be a regular, non-symlink file: $env_file" >&2
    return 1
  }

  awk '
    /^[[:space:]]*($|#)/ { next }
    $0 !~ /^[A-Za-z_][A-Za-z0-9_]*=/ {
      printf "invalid .env syntax at line %d (expected NAME=value)\n", NR > "/dev/stderr"
      failed = 1
      next
    }
    {
      key = $0
      sub(/=.*/, "", key)
      if (++seen[key] > 1) {
        printf "duplicate .env key rejected: %s\n", key > "/dev/stderr"
        failed = 1
      }
      if (key ~ /^COMPOSE_/ || key == "DOCKER_DEFAULT_PLATFORM") {
        printf "reserved deployment key rejected in .env: %s\n", key > "/dev/stderr"
        failed = 1
      }
    }
    END { exit failed ? 1 : 0 }
  ' "$env_file"

  mode=$(stat -c '%a' "$env_file")
  [[ $mode == "600" ]] || {
    echo ".env permissions must be 0600, found $mode" >&2
    return 1
  }
}

weknora_compose_variable_names() {
  local target=$1
  {
    awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ { print $1 }' "$target/.env"
    awk '
      {
        remaining = $0
        while (match(remaining, /\$\{[A-Za-z_][A-Za-z0-9_]*/)) {
          print substr(remaining, RSTART + 2, RLENGTH - 2)
          remaining = substr(remaining, RSTART + RLENGTH)
        }
      }
    ' "$target/docker-compose.yml" "$target/docker-compose.pin.yml"
    printf '%s\n' \
      COMPOSE_DISABLE_ENV_FILE \
      COMPOSE_ENV_FILES \
      COMPOSE_FILE \
      COMPOSE_PATH_SEPARATOR \
      COMPOSE_PROFILES \
      COMPOSE_PROJECT_NAME \
      DOCKER_DEFAULT_PLATFORM
  } | LC_ALL=C sort -u
}

weknora_compose() {
  local target=$1
  shift
  local name
  local variable_names
  local -a clean_environment=(env)

  variable_names=$(weknora_compose_variable_names "$target") || {
    echo "failed to collect Compose interpolation variables" >&2
    return 1
  }
  while IFS= read -r name; do
    [[ -n $name ]] && clean_environment+=(-u "$name")
  done <<< "$variable_names"

  "${clean_environment[@]}" \
    COMPOSE_PROFILES= \
    COMPOSE_PROJECT_NAME="$WEKNORA_COMPOSE_PROJECT" \
    docker compose \
      --project-name "$WEKNORA_COMPOSE_PROJECT" \
      --project-directory "$target" \
      --env-file "$target/.env" \
      -f "$target/docker-compose.yml" \
      -f "$target/docker-compose.pin.yml" \
      "$@"
}

weknora_require_compose_features() {
  local config_help
  local up_help
  docker compose version >/dev/null
  config_help=$(docker compose config --help)
  up_help=$(docker compose up --help)
  grep -qE -- '(^|[[:space:]])--format([[:space:]]|$)' <<< "$config_help" || {
    echo "Docker Compose is too old: config --format is required" >&2
    return 1
  }
  grep -qE -- '(^|[[:space:]])--wait([[:space:]]|$)' <<< "$up_help" || {
    echo "Docker Compose is too old: up --wait is required" >&2
    return 1
  }
  grep -qE -- '(^|[[:space:]])--wait-timeout([[:space:]]|$)' <<< "$up_help" || {
    echo "Docker Compose is too old: up --wait-timeout is required" >&2
    return 1
  }
}

weknora_require_python_runtime() {
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || {
    echo "Python 3.9 or newer is required" >&2
    return 1
  }
}

weknora_require_docker_daemon() {
  local server_version
  local server_major
  docker info >/dev/null
  server_version=$(docker version --format '{{.Server.Version}}')
  server_major=${server_version%%.*}
  [[ $server_major =~ ^[0-9]+$ ]] || {
    echo "could not parse Docker Engine server version: $server_version" >&2
    return 1
  }
  (( server_major >= 28 )) || {
    echo "Docker Engine 28 or newer is required for reliable loopback-only port publishing" >&2
    return 1
  }
}

weknora_assert_fresh_docker_project() {
  local existing
  local name

  existing=$(docker ps -aq --filter "label=com.docker.compose.project=$WEKNORA_COMPOSE_PROJECT")
  [[ -z $existing ]] || {
    echo "refusing to reuse existing containers for project $WEKNORA_COMPOSE_PROJECT" >&2
    return 1
  }
  existing=$(docker volume ls -q --filter "label=com.docker.compose.project=$WEKNORA_COMPOSE_PROJECT")
  [[ -z $existing ]] || {
    echo "refusing to reuse existing volumes for project $WEKNORA_COMPOSE_PROJECT" >&2
    return 1
  }
  existing=$(docker network ls -q --filter "label=com.docker.compose.project=$WEKNORA_COMPOSE_PROJECT")
  [[ -z $existing ]] || {
    echo "refusing to reuse existing networks for project $WEKNORA_COMPOSE_PROJECT" >&2
    return 1
  }

  for name in "${WEKNORA_CONTAINER_NAMES[@]}"; do
    if docker container inspect "$name" >/dev/null 2>&1; then
      echo "refusing to reuse existing container name: $name" >&2
      return 1
    fi
  done
}

weknora_assert_bootstrap_ports_available() {
  python3 - <<'PY'
import socket

for port in (18080, 18081):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        raise SystemExit(f"127.0.0.1:{port} is unavailable: {exc}")
    finally:
        sock.close()
PY
}

weknora_assert_resolved_config() {
  local target=$1
  local registration=$2
  weknora_compose "$target" config --format json |
    python3 "$WEKNORA_DEPLOYMENT_DIR/validate_compose.py" \
      config --env-file "$target/.env" --registration "$registration"
}

weknora_wait_http() {
  local url=$1
  local label=$2
  local attempt=1
  while (( attempt <= 60 )); do
    if curl --fail --silent \
      --connect-timeout 2 --max-time 5 "$url" >/dev/null; then
      return 0
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  echo "timed out waiting for $label: $url" >&2
  return 1
}

weknora_assert_registration_api() {
  local expected_disabled=$1
  local expected_mode
  local response
  local status

  if [[ $expected_disabled == "true" ]]; then
    expected_mode=invite_only
  else
    expected_mode=self_serve
  fi

  response=$(curl --fail --silent --show-error \
    --connect-timeout 2 --max-time 10 \
    http://127.0.0.1:18081/api/v1/auth/config)
  printf '%s' "$response" |
    python3 -c '
import json
import sys

expected = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except Exception as exc:
    raise SystemExit(f"invalid /api/v1/auth/config response: {exc}")
if payload.get("success") is not True or payload.get("registration_mode") != expected:
    raise SystemExit(
        "registration API mismatch: expected registration_mode=" + expected
        + "; database system_settings.auth.registration_mode may override .env"
    )
' "$expected_mode"

  if [[ $expected_disabled == "true" ]]; then
    status=$(curl --silent --show-error --output /dev/null \
      --write-out '%{http_code}' --connect-timeout 2 --max-time 10 \
      --request POST --header 'Content-Type: application/json' \
      --data '{}' http://127.0.0.1:18081/api/v1/auth/register)
    [[ $status == "403" ]] || {
      echo "registration gate failed: POST /api/v1/auth/register returned HTTP $status, expected 403" >&2
      echo "reset the database auth.registration_mode system setting, then rerun lock_registration.sh" >&2
      return 1
    }
  fi
}

weknora_assert_runtime() {
  local target=$1
  local registration=$2
  local actual_names
  local expected_names

  actual_names=$(docker ps -a \
    --filter "label=com.docker.compose.project=$WEKNORA_COMPOSE_PROJECT" \
    --format '{{.Names}}' | LC_ALL=C sort)
  expected_names=$(printf '%s\n' "${WEKNORA_CONTAINER_NAMES[@]}" | LC_ALL=C sort)
  [[ $actual_names == "$expected_names" ]] || {
    echo "runtime container set does not match the five-service production profile" >&2
    return 1
  }

  docker inspect "${WEKNORA_CONTAINER_NAMES[@]}" |
    python3 "$WEKNORA_DEPLOYMENT_DIR/validate_compose.py" \
      runtime --env-file "$target/.env" --registration "$registration" \
      --project "$WEKNORA_COMPOSE_PROJECT"

  weknora_wait_http http://127.0.0.1:18081/health "WeKnora app health"
  weknora_wait_http http://127.0.0.1:18080/ "WeKnora frontend"
  weknora_assert_registration_api "$registration"
}

weknora_fail_close() {
  local target=$1
  local name
  echo "deployment verification failed; stopping app and frontend to keep registration fail-closed" >&2
  weknora_compose "$target" stop frontend app >/dev/null 2>&1 || true
  for name in WeKnora-frontend WeKnora-app; do
    docker stop "$name" >/dev/null 2>&1 || true
  done
}
