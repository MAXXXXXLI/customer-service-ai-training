#!/usr/bin/env bash
set -euo pipefail

test_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=../common.sh
source "$test_dir/../common.sh"

# Production is Ubuntu/GNU coreutils (`mv -T`). Keep the fixture runnable from
# a macOS maintainer workstation without changing the production helper.
if ! /bin/mv --version >/dev/null 2>&1; then
  mv() {
    if [[ ${1:-} == -Tf ]]; then
      shift
      /bin/mv -f "$@"
    else
      /bin/mv "$@"
    fi
  }
fi

fixture=$(mktemp -d "${TMPDIR:-/tmp}/training-kb-release-gate.XXXXXX")
cleanup() {
  rm -rf -- "$fixture"
}
trap cleanup EXIT

LITE_ROOT=$fixture/opt/training-kb
LITE_RELEASES=$LITE_ROOT/releases
LITE_CURRENT=$LITE_ROOT/current
LITE_PREVIOUS=$LITE_ROOT/previous
mkdir -p "$LITE_RELEASES/old-current" "$LITE_RELEASES/old-previous" "$LITE_RELEASES/candidate"
ln -s releases/old-current "$LITE_CURRENT"
ln -s releases/old-previous "$LITE_PREVIOUS"

old_current_present=false
old_current_link=
old_previous_present=false
old_previous_link=
lite_capture_symlink_state "$LITE_CURRENT" old_current_present old_current_link
lite_capture_symlink_state "$LITE_PREVIOUS" old_previous_present old_previous_link
[[ $old_current_present == true && $old_current_link == releases/old-current ]]
[[ $old_previous_present == true && $old_previous_link == releases/old-previous ]]

# Model a failed release activation, then prove that both link generations are
# restored—not just current.
lite_atomic_symlink "$old_current_link" "$LITE_PREVIOUS"
lite_atomic_symlink releases/candidate "$LITE_CURRENT"
lite_restore_symlink_state "$LITE_CURRENT" "$old_current_present" "$old_current_link"
lite_restore_symlink_state "$LITE_PREVIOUS" "$old_previous_present" "$old_previous_link"
[[ $(readlink -- "$LITE_CURRENT") == releases/old-current ]]
[[ $(readlink -- "$LITE_PREVIOUS") == releases/old-previous ]]

# Bash suppresses errexit inside a function used by an if/&& condition. Force
# the first atomic step to fail and prove the helper returns nonzero without
# moving a stale target into place.
mkdir "${LITE_CURRENT}.new.$$"
if lite_atomic_symlink releases/candidate "$LITE_CURRENT" >/dev/null 2>&1; then
  printf '%s\n' 'atomic symlink helper ignored a temporary-path failure' >&2
  exit 1
fi
[[ $(readlink -- "$LITE_CURRENT") == releases/old-current ]]
rmdir "${LITE_CURRENT}.new.$$"

# Absence is also state: a failed first activation must not leave a synthetic
# previous link behind.
rm -f -- "$LITE_PREVIOUS"
lite_capture_symlink_state "$LITE_PREVIOUS" old_previous_present old_previous_link
lite_atomic_symlink releases/old-current "$LITE_PREVIOUS"
lite_restore_symlink_state "$LITE_PREVIOUS" "$old_previous_present" "$old_previous_link"
[[ ! -e $LITE_PREVIOUS && ! -L $LITE_PREVIOUS ]]

stub_bin=$fixture/bin
mkdir -p "$stub_bin"
cat >"$stub_bin/nginx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat >"$stub_bin/ss" <<'EOF'
#!/usr/bin/env bash
if [[ ${TEST_SS_MODE:-loopback} == public ]]; then
  printf '%s\n' 'LISTEN 0 511 0.0.0.0:8088 0.0.0.0:*'
else
  printf '%s\n' 'LISTEN 0 511 127.0.0.1:8088 0.0.0.0:*'
fi
EOF
cat >"$stub_bin/curl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$TEST_CURL_LOG"
printf '%s' "${TEST_CURL_STATUS:-401}"
EOF
chmod 0755 "$stub_bin/nginx" "$stub_bin/ss" "$stub_bin/curl"
export PATH=$stub_bin:$PATH
export TEST_CURL_LOG=$fixture/curl.log

quick_site=$fixture/quick-tunnel.conf
cat >"$quick_site" <<'EOF'
server {
    listen 127.0.0.1:8088;
    server_name _;
    auth_basic "Private training knowledge base";
    location / { proxy_pass http://127.0.0.1:8787; }
}
EOF
lite_verify_nginx_entry "$quick_site"
grep -q 'http://127.0.0.1:8088/' "$TEST_CURL_LOG"
grep -q 'http://127.0.0.1:8088/api/health' "$TEST_CURL_LOG"

if (TEST_SS_MODE=public lite_verify_nginx_entry "$quick_site") >/dev/null 2>&1; then
  printf '%s\n' 'public :8088 listener unexpectedly passed the Quick Tunnel gate' >&2
  exit 1
fi
if (TEST_CURL_STATUS=200 lite_verify_nginx_entry "$quick_site") >/dev/null 2>&1; then
  printf '%s\n' 'anonymous HTTP 200 unexpectedly passed the Basic Auth gate' >&2
  exit 1
fi

anonymous_quick_site=$fixture/quick-tunnel-anonymous.conf
cat >"$anonymous_quick_site" <<'EOF'
server {
    listen 127.0.0.1:8088;
    server_name _;
    # training-kb-public-mode: anonymous
    auth_basic off;
    location / { proxy_pass http://127.0.0.1:8787; }
}
EOF
TEST_CURL_STATUS=200 lite_verify_nginx_entry "$anonymous_quick_site"
if (TEST_CURL_STATUS=401 lite_verify_nginx_entry "$anonymous_quick_site") >/dev/null 2>&1; then
  printf '%s\n' 'anonymous Quick Tunnel unexpectedly accepted HTTP 401' >&2
  exit 1
fi

https_site=$fixture/https.conf
cat >"$https_site" <<'EOF'
server { listen 80; server_name kb.example.com; return 301 https://$host$request_uri; }
server {
    listen 443 ssl;
    server_name kb.example.com;
    auth_basic "Private training knowledge base";
    location / { proxy_pass http://127.0.0.1:8787; }
}
EOF
lite_verify_nginx_entry "$https_site"
grep -q -- '--resolve kb.example.com:443:127.0.0.1 https://kb.example.com/' "$TEST_CURL_LOG"

http_site=$fixture/http.conf
cat >"$http_site" <<'EOF'
server {
    listen 80 default_server;
    server_name _;
    auth_basic "Training knowledge base";
    location / { proxy_pass http://127.0.0.1:8787; }
}
EOF
lite_verify_nginx_entry "$http_site"
grep -q 'http://127.0.0.1/' "$TEST_CURL_LOG"

wait_was_called=false
systemctl() {
  return 1
}
lite_wait_http() {
  wait_was_called=true
  return 0
}
if lite_start_services; then
  printf '%s\n' 'service start failure was masked inside a conditional call' >&2
  exit 1
fi
[[ $wait_was_called == false ]]

printf '%s\n' 'release gate fixture tests passed'
