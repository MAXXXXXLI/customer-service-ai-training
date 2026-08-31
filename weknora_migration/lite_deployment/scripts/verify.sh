#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$script_dir/common.sh"

mode=strict
if [[ $# -eq 1 && $1 == --basic ]]; then
  mode=basic
elif [[ $# -ne 0 ]]; then
  printf 'usage: %s [--basic]\n' "$0" >&2
  exit 2
fi

lite_require_root
lite_load_versions
lite_require_commands curl nginx python3 readlink sha256sum sqlite3 ss stat systemctl
lite_validate_weknora_env_policy "$LITE_WEKNORA_ENV"
lite_validate_training_env_policy "$LITE_TRAINING_ENV"

[[ -L $LITE_CURRENT ]] || lite_die "$LITE_CURRENT is not an atomic release symlink"
current_release=$(readlink -f -- "$LITE_CURRENT")
lite_assert_release_dir "$current_release"

manifest=$current_release/RELEASE_MANIFEST.env
[[ $(lite_env_value "$manifest" WEKNORA_TAG) == "$WEKNORA_TAG" ]] || lite_die "release tag mismatch"
[[ $(lite_env_value "$manifest" WEKNORA_COMMIT) == "$WEKNORA_COMMIT" ]] || lite_die "release commit mismatch"
[[ $(lite_env_value "$manifest" WEKNORA_SQLITE_PATCH_COMMIT) == "$WEKNORA_SQLITE_PATCH_COMMIT" ]] || lite_die "release SQLite patch mismatch"
[[ $(lite_env_value "$manifest" WEKNORA_SQLITE_SCHEMA_VERSION) == "$WEKNORA_SQLITE_SCHEMA_VERSION" ]] || lite_die "release SQLite schema version mismatch"
[[ $(lite_env_value "$manifest" GO_VERSION) == "$GO_VERSION" ]] || lite_die "release Go version mismatch"
[[ $(lite_env_value "$manifest" NODE_VERSION) == "$NODE_VERSION" ]] || lite_die "release Node.js version mismatch"
(
  cd "$current_release"
  sha256sum --check --status RELEASE.sha256
) || lite_die "release checksum verification failed"

[[ $(lite_env_value "$LITE_WEKNORA_ENV" SERVER_HOST) == 127.0.0.1 ]] || lite_die "WeKnora host is not loopback"
[[ $(lite_env_value "$LITE_WEKNORA_ENV" SERVER_PORT) == 8080 ]] || lite_die "WeKnora port changed"
[[ $(lite_env_value "$LITE_WEKNORA_ENV" DB_DRIVER) == sqlite ]] || lite_die "WeKnora is not using SQLite"
[[ $(lite_env_value "$LITE_WEKNORA_ENV" RETRIEVE_DRIVER) == sqlite ]] || lite_die "WeKnora retrieval is not SQLite"
[[ $(lite_env_value "$LITE_WEKNORA_ENV" STREAM_MANAGER_TYPE) == memory ]] || lite_die "WeKnora queue is not in-memory"
[[ $(lite_env_value "$LITE_WEKNORA_ENV" WEKNORA_SANDBOX_MODE) == disabled ]] || lite_die "WeKnora sandbox must stay disabled"
[[ $(lite_env_value "$LITE_TRAINING_ENV" HOST) == 127.0.0.1 ]] || lite_die "training app host is not loopback"
[[ $(lite_env_value "$LITE_TRAINING_ENV" PORT) == 8787 ]] || lite_die "training app port changed"
[[ $(lite_env_value "$LITE_TRAINING_ENV" WEKNORA_BASE_URL) == http://127.0.0.1:8080 ]] || lite_die "training app points to an unexpected WeKnora URL"

[[ $(systemctl show -p User --value "$LITE_WEKNORA_SERVICE") == weknora-lite ]] || lite_die "WeKnora service user mismatch"
[[ $(systemctl show -p User --value "$LITE_TRAINING_SERVICE") == training-app ]] || lite_die "training service user mismatch"
lite_service_active "$LITE_WEKNORA_SERVICE" || lite_die "$LITE_WEKNORA_SERVICE is not active"
lite_service_active "$LITE_TRAINING_SERVICE" || lite_die "$LITE_TRAINING_SERVICE is not active"

lite_wait_http http://127.0.0.1:8080/health WeKnora
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8080/health |
  python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if p.get("status")=="ok" else 1)' || lite_die "invalid WeKnora health payload"

sqlite_db=$(lite_env_value "$LITE_WEKNORA_ENV" DB_PATH)
[[ $sqlite_db == "$LITE_STATE/weknora.db" && -f $sqlite_db && ! -L $sqlite_db ]] || {
  lite_die "unexpected SQLite database path"
}
sqlite_state=$(sqlite3 -batch -noheader "$sqlite_db" \
  'SELECT CAST(version AS TEXT)||"|"||CAST(dirty AS INTEGER) FROM schema_migrations;')
[[ $sqlite_state == "$WEKNORA_SQLITE_SCHEMA_VERSION|0" ]] || {
  lite_die "SQLite migration state is $sqlite_state, expected $WEKNORA_SQLITE_SCHEMA_VERSION|0"
}
[[ $(sqlite3 -batch -noheader "$sqlite_db" 'PRAGMA quick_check;') == ok ]] || {
  lite_die "SQLite quick_check failed"
}
sqlite3 -batch -noheader "$sqlite_db" <<'SQL' | grep -qx '14' || lite_die "SQLite patched schema is incomplete"
SELECT
  (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN (
    'task_pending_ops','task_dead_letters','system_settings',
    'knowledge_processing_spans','knowledge_tag_relations'
  ))
  + (SELECT COUNT(*) FROM pragma_table_info('messages') WHERE name='attachments')
  + (SELECT COUNT(*) FROM pragma_table_info('tenant_invitations') WHERE name IN ('token','accepted_count'))
  + (SELECT COUNT(*) FROM pragma_table_info('users') WHERE name='is_system_admin')
  + (SELECT COUNT(*) FROM pragma_table_info('knowledges') WHERE name='pending_subtasks_count')
  + (SELECT COUNT(*) FROM pragma_table_info('embed_channels') WHERE name='allow_memory')
  + (SELECT COUNT(*) FROM pragma_table_info('tenants') WHERE name='api_principal_config')
  + (SELECT COUNT(*) FROM pragma_table_info('mcp_oauth_tokens') WHERE name IN ('principal_type','principal_id'));
SQL

if [[ $mode == strict ]]; then
  lite_wait_http http://127.0.0.1:8787/api/health "training application"
  curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8787/api/health |
    python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if p.get("ok") is True and p.get("knowledge",{}).get("provider")=="weknora" and p.get("knowledge",{}).get("weknora_configured") is True else 1)' || lite_die "invalid strict training health payload"
else
  lite_wait_http_status http://127.0.0.1:8787/api/health "training application" 200 503
  training_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time 10 http://127.0.0.1:8787/api/health)
  if [[ $training_status == 200 ]]; then
    curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8787/api/health |
      python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if p.get("ok") is True else 1)' || lite_die "invalid configured training health payload"
  else
    [[ $training_status == 503 ]] || lite_die "unexpected bootstrap training health status: $training_status"
    curl --silent --show-error --max-time 10 http://127.0.0.1:8787/api/health |
      python3 -c 'import json,sys; p=json.load(sys.stdin); k=p.get("knowledge",{}); raise SystemExit(0 if p.get("ok") is False and k.get("provider")=="unavailable" and k.get("weknora_required") is True and k.get("weknora_configured") is False and k.get("configuration_error") else 1)' || lite_die "training bootstrap did not fail closed as expected"
  fi
fi

socket_report=$(ss -ltnH | awk '
  $4 ~ /^127\.0\.0\.1:8080$/ {weknora++}
  $4 ~ /^127\.0\.0\.1:8787$/ {training++}
  $4 ~ /(^|:)8080$/ && $4 !~ /^127\.0\.0\.1:8080$/ {bad_weknora++}
  $4 ~ /(^|:)8787$/ && $4 !~ /^127\.0\.0\.1:8787$/ {bad_training++}
  END {printf "%d %d %d %d", weknora, training, bad_weknora, bad_training}
')
read -r loopback_weknora loopback_training public_weknora public_training <<< "$socket_report"
[[ $loopback_weknora -ge 1 && $public_weknora -eq 0 ]] || lite_die "WeKnora is not exclusively bound to 127.0.0.1:8080"
[[ $loopback_training -ge 1 && $public_training -eq 0 ]] || lite_die "training app is not exclusively bound to 127.0.0.1:8787"

if [[ -e /etc/nginx/sites-enabled/training-kb || -L /etc/nginx/sites-enabled/training-kb ]]; then
  [[ -L /etc/nginx/sites-enabled/training-kb ]] || {
    lite_die "/etc/nginx/sites-enabled/training-kb must be a symlink to the managed site"
  }
  lite_verify_nginx_entry /etc/nginx/sites-enabled/training-kb
fi

if [[ $mode == strict ]]; then
  [[ -n $(lite_env_value "$LITE_TRAINING_ENV" SILICONFLOW_API_KEY) ]] || lite_die "SILICONFLOW_API_KEY is empty"
  [[ -n $(lite_env_value "$LITE_TRAINING_ENV" WEKNORA_RETRIEVE_API_KEY) ]] || lite_die "WEKNORA_RETRIEVE_API_KEY is empty"
  [[ -n $(lite_env_value "$LITE_TRAINING_ENV" WEKNORA_KB_IDS) ]] || lite_die "WEKNORA_KB_IDS is empty"
  [[ $(lite_env_value "$LITE_TRAINING_ENV" WEKNORA_REQUIRED) == 1 ]] || lite_die "WEKNORA_REQUIRED must be 1"

  python3 - "$LITE_TRAINING_ENV" <<'PY'
import json
import pathlib
import sys
import urllib.error
import urllib.request

values = {}
for raw in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if raw and not raw.startswith("#"):
        key, value = raw.split("=", 1)
        values[key] = value

allowed = {item.strip() for item in values["WEKNORA_KB_IDS"].replace(";", ",").split(",") if item.strip()}
payload = json.dumps({"query": "服务安全", "knowledge_base_ids": sorted(allowed)}, ensure_ascii=False).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8080/api/v1/knowledge-search",
    data=payload,
    headers={
        "Content-Type": "application/json; charset=utf-8",
        "X-API-Key": values["WEKNORA_RETRIEVE_API_KEY"],
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
    raise SystemExit(f"strict WeKnora retrieval failed: {exc}")
if result.get("success") is not True or not isinstance(result.get("data"), list):
    raise SystemExit("strict WeKnora retrieval returned an invalid envelope")
if not result["data"]:
    raise SystemExit("strict WeKnora retrieval returned no knowledge chunks")
for row in result["data"]:
    if not isinstance(row, dict) or not str(row.get("content") or "").strip():
        raise SystemExit("strict WeKnora retrieval returned an invalid knowledge chunk")
    if str(row.get("knowledge_base_id") or "") not in allowed:
        raise SystemExit("strict WeKnora retrieval escaped the configured KB allow-list")
PY
fi

printf '%s\n' "verification passed ($mode): $(basename -- "$current_release")"
