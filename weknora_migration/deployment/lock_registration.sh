#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $# -ne 1 || $1 != /* ]]; then
  echo "Usage: $0 /absolute/path/to/weknora" >&2
  exit 2
fi

target=$1
script_dir=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=compose_common.sh
source "$script_dir/compose_common.sh"

temporary=
fail_close_armed=false
lock_verified=false
cleanup() {
  local status=$?
  if [[ -n ${temporary:-} ]]; then
    rm -f -- "$temporary" || true
  fi
  if (( status != 0 )) && [[ $fail_close_armed == "true" && $lock_verified != "true" ]]; then
    weknora_fail_close "$target"
  fi
  trap - EXIT
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[[ -f $target/docker-compose.yml ]] || { echo "official docker-compose.yml missing: $target" >&2; exit 1; }
[[ -f $target/docker-compose.pin.yml ]] || { echo "docker-compose.pin.yml missing: $target" >&2; exit 1; }
[[ -f $target/.env ]] || { echo ".env missing: $target" >&2; exit 1; }

for command in awk curl df docker env git grep mktemp python3 sort stat; do
  command -v "$command" >/dev/null 2>&1 || { echo "required command missing: $command" >&2; exit 1; }
done
weknora_require_python_runtime
weknora_require_compose_features
weknora_require_docker_daemon
weknora_validate_env_file "$target"
fail_close_armed=true

registration=$(weknora_env_value "$target" DISABLE_REGISTRATION)
case "$registration" in
  false)
    "$script_dir/preflight.sh" --bootstrap "$target"
    ;;
  true)
    # Idempotent reruns are allowed; the production preflight is repeated below.
    ;;
  *)
    echo "DISABLE_REGISTRATION must be true or false" >&2
    exit 1
    ;;
esac

if [[ $registration == "false" ]]; then
  temporary=$(mktemp "$target/.env.tmp.XXXXXX")
  seen_registration=0
  while IFS= read -r line || [[ -n $line ]]; do
    case "$line" in
      DISABLE_REGISTRATION=*)
        printf 'DISABLE_REGISTRATION=true\n'
        seen_registration=$((seen_registration + 1))
        ;;
      *)
        printf '%s\n' "$line"
        ;;
    esac
  done < "$target/.env" > "$temporary"
  [[ $seen_registration == 1 ]] || {
    echo "DISABLE_REGISTRATION must occur exactly once in .env" >&2
    exit 1
  }
  mv "$temporary" "$target/.env"
  temporary=
  chmod 600 "$target/.env"
fi

"$script_dir/preflight.sh" "$target"
weknora_compose "$target" up \
  -d --no-build --force-recreate --wait --wait-timeout 600 \
  app frontend
weknora_assert_runtime "$target" true
lock_verified=true

echo "public password registration locked and verified: /api/v1/auth/config=invite_only, /api/v1/auth/register=403"
