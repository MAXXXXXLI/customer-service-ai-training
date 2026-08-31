#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=compose_common.sh
source "$script_dir/compose_common.sh"

usage() {
  echo "Usage: $0 [--bootstrap] /absolute/path/to/weknora-checkout" >&2
  exit 2
}

bootstrap=false
if [[ ${1:-} == "--bootstrap" ]]; then
  bootstrap=true
  shift
fi
[[ $# -eq 1 ]] || usage
target=$1
[[ $target == /* ]] || { echo "target must be an absolute path" >&2; exit 2; }
[[ -d $target ]] || { echo "target directory not found: $target" >&2; exit 1; }
[[ -f $target/docker-compose.yml ]] || { echo "official docker-compose.yml missing" >&2; exit 1; }
[[ -f $target/.env ]] || { echo ".env missing" >&2; exit 1; }
[[ -f $target/docker-compose.pin.yml && ! -L $target/docker-compose.pin.yml ]] || { echo "docker-compose.pin.yml must be a regular, non-symlink file" >&2; exit 1; }

for command in docker git awk cmp df env grep nproc python3 sort stat; do
  command -v "$command" >/dev/null 2>&1 || { echo "required command missing: $command" >&2; exit 1; }
done
weknora_require_python_runtime
cmp -s "$script_dir/docker-compose.pin.yml" "$target/docker-compose.pin.yml" || {
  echo "docker-compose.pin.yml differs from the approved deployment override" >&2
  exit 1
}
weknora_require_compose_features
weknora_require_docker_daemon

if [[ $(uname -s) != "Linux" ]]; then
  echo "production target must be Linux" >&2
  exit 1
fi

memory_kib=$(awk '/MemTotal:/ {print $2}' /proc/meminfo)
if (( memory_kib < 15000000 )); then
  echo "at least 16 GB RAM is required; 32 GB is recommended" >&2
  exit 1
fi

cpu_count=$(nproc)
if (( cpu_count < 4 )); then
  echo "at least 4 CPU cores are required; 8 are recommended" >&2
  exit 1
fi

available_kib=$(df -Pk "$target" | awk 'NR==2 {print $4}')
if (( available_kib < 80000000 )); then
  echo "at least 80 GB free disk is required; 200 GB NVMe is recommended" >&2
  exit 1
fi

docker_root=$(docker info --format '{{.DockerRootDir}}')
[[ -n $docker_root ]] || { echo "Docker Root Dir could not be determined" >&2; exit 1; }
docker_available_kib=$(df -Pk "$docker_root" | awk 'NR==2 {print $4}')
if (( docker_available_kib < 80000000 )); then
  echo "Docker Root Dir needs at least 80 GB free; 200 GB NVMe is recommended" >&2
  exit 1
fi

weknora_validate_env_file "$target"
approved_env_keys=$(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ { print $1 }' \
  "$script_dir/.env.production.example" | LC_ALL=C sort)
actual_env_keys=$(awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ { print $1 }' \
  "$target/.env" | LC_ALL=C sort)
[[ $actual_env_keys == "$approved_env_keys" ]] || {
  echo ".env keys must exactly match the approved production template" >&2
  exit 1
}

env_value() {
  weknora_env_value "$target" "$1"
}

require_value() {
  local name=$1
  local value
  value=$(env_value "$name")
  [[ -n $value ]] || { echo "$name is missing" >&2; exit 1; }
  case "$value" in
    *CHANGE_ME*|postgres123\!*|redis123\!*|weknora-jwt-secret|your-secret-token-at-least-16-bytes)
      echo "$name still contains an example secret" >&2
      exit 1
      ;;
  esac
}

for name in DB_PASSWORD REDIS_PASSWORD JWT_SECRET SYSTEM_AES_KEY GRPC_AUTH_TOKEN; do
  require_value "$name"
done

[[ $(env_value WEKNORA_VERSION) == "v0.7.2" ]] || { echo "WEKNORA_VERSION must be v0.7.2" >&2; exit 1; }
[[ $(env_value GIN_MODE) == "release" ]] || { echo "GIN_MODE must be release" >&2; exit 1; }
[[ $(env_value LLM_DEBUG_LOG) == "false" ]] || { echo "LLM_DEBUG_LOG must remain disabled" >&2; exit 1; }
[[ $(env_value AUTO_MIGRATE) == "true" ]] || { echo "AUTO_MIGRATE must be enabled" >&2; exit 1; }
[[ $(env_value AUTO_RECOVER_DIRTY) == "true" ]] || { echo "AUTO_RECOVER_DIRTY must be enabled" >&2; exit 1; }
[[ $(env_value FRONTEND_PORT) == "127.0.0.1:18080" ]] || { echo "FRONTEND_PORT must remain loopback-only" >&2; exit 1; }
[[ $(env_value APP_PORT) == "127.0.0.1:18081" ]] || { echo "APP_PORT must remain loopback-only" >&2; exit 1; }
[[ $(env_value APP_HOST) == "app" ]] || { echo "APP_HOST must be app" >&2; exit 1; }
[[ $(env_value APP_BACKEND_PORT) == "8080" ]] || { echo "APP_BACKEND_PORT must be 8080" >&2; exit 1; }
[[ $(env_value APP_SCHEME) == "http" ]] || { echo "APP_SCHEME must be http on the internal Compose network" >&2; exit 1; }
[[ $(env_value RESOURCE_URL_MODE) == "handle" ]] || { echo "RESOURCE_URL_MODE must be handle" >&2; exit 1; }
[[ $(env_value DB_DRIVER) == "postgres" ]] || { echo "DB_DRIVER must be postgres" >&2; exit 1; }
[[ $(env_value DB_HOST) == "postgres" ]] || { echo "DB_HOST must be the internal postgres service" >&2; exit 1; }
[[ $(env_value DB_PORT) == "5432" ]] || { echo "DB_PORT must be 5432" >&2; exit 1; }
[[ $(env_value DB_USER) == "weknora" ]] || { echo "DB_USER must be weknora" >&2; exit 1; }
[[ $(env_value DB_NAME) == "WeKnora" ]] || { echo "DB_NAME must be WeKnora" >&2; exit 1; }
[[ $(env_value STREAM_MANAGER_TYPE) == "redis" ]] || { echo "STREAM_MANAGER_TYPE must be redis" >&2; exit 1; }
[[ $(env_value REDIS_ADDR) == "redis:6379" ]] || { echo "REDIS_ADDR must be the internal redis service" >&2; exit 1; }
[[ $(env_value STORAGE_TYPE) == "local" ]] || { echo "STORAGE_TYPE must be local for this deployment profile" >&2; exit 1; }
[[ $(env_value LOCAL_STORAGE_BASE_DIR) == "/data/files" ]] || { echo "LOCAL_STORAGE_BASE_DIR must be /data/files" >&2; exit 1; }
[[ $(env_value RETRIEVE_DRIVER) == "postgres" ]] || { echo "RETRIEVE_DRIVER must be postgres" >&2; exit 1; }
[[ $(env_value NEO4J_ENABLE) == "false" ]] || { echo "NEO4J must remain disabled for the first release" >&2; exit 1; }
[[ $(env_value WEKNORA_AUTH_DEFAULT_TENANT_MODE) == "create_personal" ]] || { echo "default tenant mode must be create_personal" >&2; exit 1; }
[[ $(env_value WEKNORA_TENANT_SELF_SERVICE_CREATION_ENABLED) == "false" ]] || { echo "tenant self-service creation must be disabled" >&2; exit 1; }
[[ $(env_value WEKNORA_TENANT_ENABLE_RBAC) == "true" ]] || { echo "RBAC must be enabled" >&2; exit 1; }
[[ $(env_value WEKNORA_TENANT_ENABLE_CROSS_TENANT_ACCESS) == "false" ]] || { echo "cross-tenant access must be disabled" >&2; exit 1; }
[[ $(env_value WEKNORA_TENANT_AUTO_CREATE_API_KEY) == "false" ]] || { echo "automatic API key creation must be disabled" >&2; exit 1; }
[[ $(env_value OIDC_AUTH_ENABLE) == "false" ]] || { echo "OIDC must remain disabled for the first release" >&2; exit 1; }
[[ $(env_value WEKNORA_SANDBOX_MODE) == "disabled" ]] || { echo "sandbox must be disabled for the first release" >&2; exit 1; }

jwt=$(env_value JWT_SECRET)
[[ $jwt =~ ^[0-9a-f]{96}$ ]] || { echo "JWT_SECRET must be the 96-character lowercase hex value generated by prepare_server.sh" >&2; exit 1; }
db_password=$(env_value DB_PASSWORD)
[[ $db_password =~ ^[0-9a-f]{48}$ ]] || { echo "DB_PASSWORD must be the 48-character lowercase hex value generated by prepare_server.sh" >&2; exit 1; }
redis_password=$(env_value REDIS_PASSWORD)
[[ $redis_password =~ ^[0-9a-f]{48}$ ]] || { echo "REDIS_PASSWORD must be the 48-character lowercase hex value generated by prepare_server.sh" >&2; exit 1; }
[[ $db_password != "$redis_password" ]] || { echo "DB_PASSWORD and REDIS_PASSWORD must be different" >&2; exit 1; }
aes=$(env_value SYSTEM_AES_KEY)
[[ $aes != "00000000000000000000000000000000" ]] || { echo "SYSTEM_AES_KEY is still the invalid example" >&2; exit 1; }
[[ $aes != "weknora-system-aes-key-32bytes!!" ]] || { echo "SYSTEM_AES_KEY is still the official weak example" >&2; exit 1; }
[[ $aes =~ ^[0-9a-f]{32}$ ]] || { echo "SYSTEM_AES_KEY must be the 32-character lowercase hex value generated by prepare_server.sh" >&2; exit 1; }
grpc=$(env_value GRPC_AUTH_TOKEN)
[[ $grpc =~ ^[0-9a-f]{48}$ ]] || { echo "GRPC_AUTH_TOKEN must be the 48-character lowercase hex value generated by prepare_server.sh" >&2; exit 1; }
bootstrap_admin_email=$(env_value WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL)
if [[ -n $bootstrap_admin_email && ! $bootstrap_admin_email =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
  echo "WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL must be empty or a valid email address" >&2
  exit 1
fi

registration=$(env_value DISABLE_REGISTRATION)
if $bootstrap; then
  [[ $registration == "false" ]] || { echo "bootstrap requires DISABLE_REGISTRATION=false" >&2; exit 1; }
else
  [[ $registration == "true" ]] || { echo "production requires DISABLE_REGISTRATION=true" >&2; exit 1; }
fi

git_commit=$(git -C "$target" rev-parse HEAD)
[[ $git_commit == "3d5d8bfcdfeeea266b292b71cea616847af28d0f" ]] || {
  echo "checkout is not the approved v0.7.2 commit: $git_commit" >&2
  exit 1
}
git -C "$target" diff --quiet --exit-code || {
  echo "approved v0.7.2 tracked files have local modifications" >&2
  exit 1
}
git -C "$target" diff --cached --quiet --exit-code || {
  echo "approved v0.7.2 tracked files have staged modifications" >&2
  exit 1
}

weknora_assert_resolved_config "$target" "$registration"

echo "preflight passed: v0.7.2, five images pinned, loopback-only, secrets replaced, resolved compose valid"
