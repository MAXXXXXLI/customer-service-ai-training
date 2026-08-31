#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
deployment_dir=$(cd -- "$script_dir/.." && pwd -P)
project_dir=$(cd -- "$deployment_dir/../.." && pwd -P)

failed=0
while IFS= read -r -d '' script; do
  if ! bash -n "$script"; then
    failed=1
  fi
done < <(find "$script_dir" -type f -name '*.sh' -print0)
(( failed == 0 )) || exit 1

if find "$script_dir" -type f -name '*.sh' ! -perm -u+x -print -quit | grep -q .; then
  printf '%s\n' 'all deployment shell scripts must be executable' >&2
  exit 1
fi

grep -q '^User=weknora-lite$' "$deployment_dir/systemd/weknora-lite.service"
grep -q '^User=training-app$' "$deployment_dir/systemd/training-app.service"
grep -q '^EnvironmentFile=/etc/training-kb/weknora.env$' "$deployment_dir/systemd/weknora-lite.service"
grep -q '^Environment=JIEBA_DICT_DIR=/opt/training-kb/current/weknora/jieba-dict$' "$deployment_dir/systemd/weknora-lite.service"
grep -q '^EnvironmentFile=/etc/training-kb/training.env$' "$deployment_dir/systemd/training-app.service"
grep -q '^SERVER_HOST=127.0.0.1$' "$deployment_dir/templates/weknora.env.example"
grep -q '^SERVER_PORT=8080$' "$deployment_dir/templates/weknora.env.example"
grep -q '^SYSTEM_AES_KEY=GENERATED_DURING_PREPARE$' "$deployment_dir/templates/weknora.env.example"
grep -q '^CONCURRENCY_POOL_SIZE=1$' "$deployment_dir/templates/weknora.env.example"
grep -q '^HOST=127.0.0.1$' "$deployment_dir/templates/training.env.example"
grep -q '^PORT=8787$' "$deployment_dir/templates/training.env.example"
grep -q '^IFLYTEK_TTS_ENDPOINT=wss://tts-api.xfyun.cn/v2/tts$' "$deployment_dir/templates/training.env.example"
grep -q '^IFLYTEK_TTS_MAX_TEXT_BYTES=7999$' "$deployment_dir/templates/training.env.example"
grep -q '^IFLYTEK_IAT_ENDPOINT=wss://iat-api.xfyun.cn/v2/iat$' "$deployment_dir/templates/training.env.example"
grep -q '^IFLYTEK_IAT_SAMPLE_RATE=16000$' "$deployment_dir/templates/training.env.example"
grep -q '^IFLYTEK_IAT_MAX_DURATION_SECONDS=30$' "$deployment_dir/templates/training.env.example"
[[ -f "$project_dir/local_app/iflytek_tts.py" ]]
[[ -f "$project_dir/local_app/iflytek_asr.py" ]]
[[ -f "$deployment_dir/scripts/set_iflytek_tts_credentials.py" ]]
[[ -f "$deployment_dir/scripts/set_iflytek_asr_credentials.py" ]]
python3 -m py_compile "$project_dir/local_app/iflytek_tts.py" "$project_dir/local_app/iflytek_asr.py" "$project_dir/local_app/server.py" \
  "$deployment_dir/scripts/set_iflytek_tts_credentials.py" "$deployment_dir/scripts/set_iflytek_asr_credentials.py"
grep -q '^WEKNORA_SOURCE_ARCHIVE_SHA256=e8cfb2830a103a8176e9b4dde0b50c44339221731285df46bc3960c9a2731d01$' "$deployment_dir/versions.env"
grep -q '^WEKNORA_SQLITE_PATCH_COMMIT=71fe7f31ee7f4eaced1827b6a83c93dc41e5f204$' "$deployment_dir/versions.env"
grep -q '^WEKNORA_SQLITE_SCHEMA_VERSION=11$' "$deployment_dir/versions.env"
grep -q 'cached WeKnora source archive checksum mismatch' "$script_dir/prepare_release.sh"
grep -q 'SQLite migration patch checksum mismatch' "$script_dir/prepare_release.sh"
patch_root=$deployment_dir/upstream_patches/sqlite-71fe7f31ee7f4eaced1827b6a83c93dc41e5f204
[[ $(find "$patch_root/migrations/sqlite" -maxdepth 1 -type f -name '*.sql' | wc -l) -eq 18 ]]
(
  cd "$patch_root"
  sha256sum --check --strict --status SHA256SUMS
)
grep -q -- '-L 18080:127.0.0.1:8787' "$deployment_dir/README.md"
grep -q -- '-L 18081:127.0.0.1:8080' "$deployment_dir/README.md"
grep -q 'lite_wait_http_status http://127.0.0.1:8787/api/health "training application" 200 503' "$script_dir/common.sh"
grep -q 'training bootstrap did not fail closed as expected' "$script_dir/verify.sh"
grep -q 'lite_verify_nginx_entry /etc/nginx/sites-enabled/training-kb' "$script_dir/verify.sh"
grep -q 'Quick Tunnel origin is not exclusively bound to 127.0.0.1:8088' "$script_dir/common.sh"
grep -q 'training-kb-public-mode:' "$script_dir/common.sh"
grep -q '^lite_acquire_release_lock$' "$script_dir/prepare_release.sh"
grep -q '^lite_acquire_release_lock$' "$script_dir/rollback.sh"
grep -q '^lite_acquire_release_lock$' "$script_dir/backup.sh"
grep -q 'backup cleanup could not restore the original service state' "$script_dir/backup.sh"
grep -q 'original service state failed recovery verification' "$script_dir/backup.sh"
grep -q '^tunnel_was_active=false$' "$script_dir/backup.sh"
grep -q 'systemctl start training-quick-tunnel.service' "$script_dir/backup.sh"
grep -q 'TUNNEL_WAS_ACTIVE=%s' "$script_dir/backup.sh"
grep -q '^chown -R root:root "\$stage_dir"$' "$script_dir/prepare_release.sh"
grep -q 'release contains a non-root-owned path' "$script_dir/common.sh"
grep -Fq 'http://127.0.0.1:8088${probe_path}' "$script_dir/common.sh"
grep -q 'the original current and previous links were restored' "$script_dir/prepare_release.sh"
grep -q 'the original current and previous links were restored' "$script_dir/rollback.sh"
grep -q 'proxy_pass http://127.0.0.1:8787;' "$deployment_dir/nginx/training-kb.conf.template"
if grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:8080' "$deployment_dir/nginx/training-kb.conf.template"; then
  printf '%s\n' 'Nginx must not expose WeKnora' >&2
  exit 1
fi
grep -q 'usage: %s <public-domain>' "$script_dir/enable_public_entry.sh"
grep -q '^backend=http://127.0.0.1:8787$' "$script_dir/enable_public_entry.sh"
grep -q '^backend=http://127.0.0.1:8787$' "$script_dir/enable_quick_tunnel.sh"
grep -q '^origin=http://127.0.0.1:8088$' "$script_dir/enable_quick_tunnel.sh"
grep -q 'usage: %s \[--anonymous\]' "$script_dir/enable_quick_tunnel.sh"
grep -q 'limit_req zone=training_kb_api' "$script_dir/enable_quick_tunnel.sh"
grep -q 'client_max_body_size 512k' "$script_dir/enable_quick_tunnel.sh"
grep -q 'enable_public_entry.sh kb.example.com' "$deployment_dir/README.md"
grep -q 'enable_quick_tunnel.sh' "$deployment_dir/README.md"
if grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:8080|--url[[:space:]]+http://127\.0\.0\.1:8080' \
  "$script_dir/enable_public_entry.sh" "$script_dir/enable_quick_tunnel.sh"; then
  printf '%s\n' 'public entry scripts must not expose WeKnora' >&2
  exit 1
fi
if grep -R -n 'TENANT_AES_KEY' "$deployment_dir" --exclude='README.md' --exclude='static_check.sh'; then
  printf '%s\n' 'deprecated TENANT_AES_KEY must not be deployed' >&2
  exit 1
fi
if grep -R -n -E '(sk-[A-Za-z0-9]{16,}|SILICONFLOW_API_KEY=[A-Za-z0-9_-]{16,}|WEKNORA_RETRIEVE_API_KEY=[A-Za-z0-9_-]{16,})' \
  "$deployment_dir" --exclude='static_check.sh'; then
  printf '%s\n' 'possible embedded credential found' >&2
  exit 1
fi

"$script_dir/tests/release_gate_fixture_test.sh"

printf '%s\n' 'static deployment checks passed'
