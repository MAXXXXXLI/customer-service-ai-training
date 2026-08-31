#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 1 || $1 != /* ]]; then
  echo "Usage: $0 /absolute/new/path/for/weknora" >&2
  exit 2
fi

target=$1
script_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=compose_common.sh
source "$script_dir/compose_common.sh"

temporary=
runtime_may_be_open=false
deployment_verified=false
cleanup() {
  local status=$?
  if [[ -n ${temporary:-} ]]; then
    rm -f -- "$temporary" || true
  fi
  if (( status != 0 )) && [[ $runtime_may_be_open == "true" && $deployment_verified != "true" ]]; then
    weknora_fail_close "$target"
  fi
  trap - EXIT
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -e $target ]]; then
  echo "refusing to overwrite existing target: $target" >&2
  exit 1
fi

for command in awk curl df docker env git grep mktemp openssl python3 sort stat; do
  command -v "$command" >/dev/null 2>&1 || { echo "required command missing: $command" >&2; exit 1; }
done
weknora_require_python_runtime
weknora_require_compose_features
weknora_require_docker_daemon
weknora_assert_fresh_docker_project
weknora_assert_bootstrap_ports_available

git clone --depth 1 --branch v0.7.2 https://github.com/Tencent/WeKnora.git "$target"
commit=$(git -C "$target" rev-parse HEAD)
if [[ $commit != "3d5d8bfcdfeeea266b292b71cea616847af28d0f" ]]; then
  echo "unexpected v0.7.2 commit: $commit" >&2
  exit 1
fi

cp "$script_dir/docker-compose.pin.yml" "$target/docker-compose.pin.yml"

# Generate secrets in shell variables, then write one mode-0600 temp file.
# No secret is passed through a child-process argument or printed.
db_password=$(openssl rand -hex 24)
redis_password=$(openssl rand -hex 24)
jwt_secret=$(openssl rand -hex 48)
system_aes_key=$(openssl rand -hex 16)
grpc_auth_token=$(openssl rand -hex 24)

temporary=$(mktemp "$target/.env.tmp.XXXXXX")
seen_db=0
seen_redis=0
seen_jwt=0
seen_aes=0
seen_grpc=0
seen_registration=0
while IFS= read -r line || [[ -n $line ]]; do
  case "$line" in
    DB_PASSWORD=*)
      printf 'DB_PASSWORD=%s\n' "$db_password"
      seen_db=$((seen_db + 1))
      ;;
    REDIS_PASSWORD=*)
      printf 'REDIS_PASSWORD=%s\n' "$redis_password"
      seen_redis=$((seen_redis + 1))
      ;;
    JWT_SECRET=*)
      printf 'JWT_SECRET=%s\n' "$jwt_secret"
      seen_jwt=$((seen_jwt + 1))
      ;;
    SYSTEM_AES_KEY=*)
      printf 'SYSTEM_AES_KEY=%s\n' "$system_aes_key"
      seen_aes=$((seen_aes + 1))
      ;;
    GRPC_AUTH_TOKEN=*)
      printf 'GRPC_AUTH_TOKEN=%s\n' "$grpc_auth_token"
      seen_grpc=$((seen_grpc + 1))
      ;;
    DISABLE_REGISTRATION=*)
      # Bootstrap stays safe because app and frontend are asserted loopback-only.
      printf 'DISABLE_REGISTRATION=false\n'
      seen_registration=$((seen_registration + 1))
      ;;
    *)
      printf '%s\n' "$line"
      ;;
  esac
done < "$script_dir/.env.production.example" > "$temporary"

if [[ $seen_db != 1 || $seen_redis != 1 || $seen_jwt != 1 || $seen_aes != 1 || $seen_grpc != 1 || $seen_registration != 1 ]]; then
  echo "deployment template does not contain each required secret/registration key exactly once" >&2
  exit 1
fi

mv "$temporary" "$target/.env"
temporary=
chmod 600 "$target/.env"
unset db_password redis_password jwt_secret system_aes_key grpc_auth_token

"$script_dir/preflight.sh" --bootstrap "$target"
weknora_compose "$target" pull frontend app docreader postgres redis

runtime_may_be_open=true
weknora_compose "$target" up \
  -d --no-build --wait --wait-timeout 600 \
  frontend app docreader postgres redis
weknora_assert_runtime "$target" false
deployment_verified=true

echo "WeKnora bootstrap is healthy on http://127.0.0.1:18080"
echo "Create the first owner through an SSH tunnel, then run lock_registration.sh."
echo "Secrets are stored only in $target/.env with mode 0600 and were not printed."
