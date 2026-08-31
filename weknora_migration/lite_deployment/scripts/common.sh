#!/usr/bin/env bash

# Shared helpers. Callers must set `set -euo pipefail` before sourcing.

LITE_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
LITE_DEPLOYMENT_DIR=$(cd -- "$LITE_SCRIPT_DIR/.." && pwd -P)

LITE_ROOT=/opt/training-kb
LITE_RELEASES=$LITE_ROOT/releases
LITE_CURRENT=$LITE_ROOT/current
LITE_PREVIOUS=$LITE_ROOT/previous
LITE_STATE=/var/lib/training-kb/weknora
LITE_ETC=/etc/training-kb
LITE_BACKUPS=/var/backups/training-kb
LITE_WEKNORA_ENV=$LITE_ETC/weknora.env
LITE_TRAINING_ENV=$LITE_ETC/training.env
LITE_WEKNORA_SERVICE=weknora-lite.service
LITE_TRAINING_SERVICE=training-app.service

lite_die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

lite_require_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || lite_die "run this command as root (sudo)"
}

lite_require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || lite_die "required command is missing: $command_name"
  done
}

lite_load_versions() {
  local versions_file=$LITE_DEPLOYMENT_DIR/versions.env
  [[ -f $versions_file && ! -L $versions_file ]] || lite_die "missing versions file: $versions_file"
  awk '
    /^[[:space:]]*($|#)/ {next}
    $0 !~ /^[A-Z][A-Z0-9_]*=[A-Za-z0-9.:_\/@-]+$/ {exit 1}
    {key=$0; sub(/=.*/, "", key); if (++seen[key] > 1) exit 1}
  ' "$versions_file" || lite_die "versions.env has unsafe syntax or duplicate keys"

  WEKNORA_TAG=$(lite_env_value "$versions_file" WEKNORA_TAG)
  WEKNORA_COMMIT=$(lite_env_value "$versions_file" WEKNORA_COMMIT)
  WEKNORA_REPOSITORY=$(lite_env_value "$versions_file" WEKNORA_REPOSITORY)
  WEKNORA_SOURCE_ARCHIVE_SHA256=$(lite_env_value "$versions_file" WEKNORA_SOURCE_ARCHIVE_SHA256)
  WEKNORA_SQLITE_PATCH_COMMIT=$(lite_env_value "$versions_file" WEKNORA_SQLITE_PATCH_COMMIT)
  WEKNORA_SQLITE_SCHEMA_VERSION=$(lite_env_value "$versions_file" WEKNORA_SQLITE_SCHEMA_VERSION)
  GO_VERSION=$(lite_env_value "$versions_file" GO_VERSION)
  GO_LINUX_AMD64_SHA256=$(lite_env_value "$versions_file" GO_LINUX_AMD64_SHA256)
  GO_LINUX_ARM64_SHA256=$(lite_env_value "$versions_file" GO_LINUX_ARM64_SHA256)
  NODE_VERSION=$(lite_env_value "$versions_file" NODE_VERSION)
  NODE_LINUX_AMD64_SHA256=$(lite_env_value "$versions_file" NODE_LINUX_AMD64_SHA256)
  NODE_LINUX_ARM64_SHA256=$(lite_env_value "$versions_file" NODE_LINUX_ARM64_SHA256)

  [[ ${WEKNORA_TAG:-} == v0.7.2 ]] || lite_die "unexpected WeKnora tag"
  [[ ${WEKNORA_COMMIT:-} == 3d5d8bfcdfeeea266b292b71cea616847af28d0f ]] || lite_die "unexpected WeKnora commit"
  [[ ${WEKNORA_REPOSITORY:-} == https://github.com/Tencent/WeKnora.git ]] || lite_die "unexpected WeKnora repository"
  [[ ${WEKNORA_SOURCE_ARCHIVE_SHA256:-} == e8cfb2830a103a8176e9b4dde0b50c44339221731285df46bc3960c9a2731d01 ]] || lite_die "unexpected WeKnora source archive checksum"
  [[ ${WEKNORA_SQLITE_PATCH_COMMIT:-} == 71fe7f31ee7f4eaced1827b6a83c93dc41e5f204 ]] || lite_die "unexpected SQLite patch commit"
  [[ ${WEKNORA_SQLITE_SCHEMA_VERSION:-} == 11 ]] || lite_die "unexpected SQLite schema version"
  [[ ${GO_VERSION:-} == 1.26.0 ]] || lite_die "unexpected Go version"
  [[ ${NODE_VERSION:-} == 22.23.2 ]] || lite_die "unexpected Node.js version"
  [[ ${GO_LINUX_AMD64_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || lite_die "invalid Go amd64 checksum"
  [[ ${GO_LINUX_ARM64_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || lite_die "invalid Go arm64 checksum"
  [[ ${NODE_LINUX_AMD64_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || lite_die "invalid Node.js amd64 checksum"
  [[ ${NODE_LINUX_ARM64_SHA256:-} =~ ^[0-9a-f]{64}$ ]] || lite_die "invalid Node.js arm64 checksum"
}

lite_validate_release_id() {
  local release_id=$1
  [[ $release_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]{5,79}$ ]] || {
    lite_die "release id must be 6-80 safe characters: $release_id"
  }
}

lite_assert_release_dir() {
  local release_dir=$1
  local resolved unexpected_owner unexpected_writable
  [[ -d $release_dir && ! -L $release_dir ]] || lite_die "release directory is missing: $release_dir"
  resolved=$(readlink -f -- "$release_dir")
  [[ $resolved == "$LITE_RELEASES/"* ]] || lite_die "release escapes $LITE_RELEASES: $resolved"
  [[ -x $resolved/weknora/WeKnora-lite ]] || lite_die "WeKnora binary is missing from release"
  [[ -f $resolved/weknora/web/index.html ]] || lite_die "WeKnora UI is missing from release"
  [[ -f $resolved/training-app/local_app/server.py ]] || lite_die "training server is missing from release"
  [[ -f $resolved/training-app/local_app/weknora_client.py ]] || lite_die "WeKnora training adapter is missing from release"
  [[ -f $resolved/RELEASE_MANIFEST.env ]] || lite_die "release manifest is missing"
  [[ -f $resolved/RELEASE.sha256 ]] || lite_die "release checksums are missing"
  unexpected_owner=$(find "$resolved" \( ! -user root -o ! -group root \) -print -quit)
  [[ -z $unexpected_owner ]] || lite_die "release contains a non-root-owned path: $unexpected_owner"
  unexpected_writable=$(find "$resolved" -perm /022 -print -quit)
  [[ -z $unexpected_writable ]] || lite_die "release contains a group/world-writable path: $unexpected_writable"
}

lite_atomic_symlink() {
  local target=$1
  local link_path=$2
  local temporary_link=${link_path}.new.$$
  [[ $link_path == "$LITE_ROOT/"* ]] || lite_die "refusing to write symlink outside $LITE_ROOT"
  rm -f -- "$temporary_link" || return
  if ! ln -s -- "$target" "$temporary_link"; then
    rm -f -- "$temporary_link" 2>/dev/null || true
    return 1
  fi
  if ! mv -Tf -- "$temporary_link" "$link_path"; then
    rm -f -- "$temporary_link" 2>/dev/null || true
    return 1
  fi
}

lite_acquire_release_lock() {
  local lock_file=$LITE_ROOT/.release.lock
  local inherited_lock=
  [[ -d $LITE_ROOT && ! -L $LITE_ROOT ]] || lite_die "release root is unsafe: $LITE_ROOT"
  [[ ! -L $lock_file ]] || lite_die "release lock must not be a symlink: $lock_file"
  if [[ ${LITE_RELEASE_LOCK_FD:-} =~ ^[0-9]+$ && -e /proc/$$/fd/$LITE_RELEASE_LOCK_FD ]]; then
    inherited_lock=$(readlink -f -- "/proc/$$/fd/$LITE_RELEASE_LOCK_FD" 2>/dev/null || true)
    if [[ -e $lock_file && $inherited_lock == "$(readlink -f -- "$lock_file")" ]]; then
      return
    fi
  fi
  exec {LITE_RELEASE_LOCK_FD}>"$lock_file" || lite_die "cannot open release lock: $lock_file"
  chmod 0600 "$lock_file" || lite_die "cannot secure release lock: $lock_file"
  flock -n "$LITE_RELEASE_LOCK_FD" || lite_die "another release or rollback is already running"
  export LITE_RELEASE_LOCK_FD
}

lite_capture_symlink_state() {
  local link_path=$1
  local present_variable=$2
  local target_variable=$3
  local captured_target=
  [[ $present_variable =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    lite_die "invalid symlink state variable: $present_variable"
  }
  [[ $target_variable =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || {
    lite_die "invalid symlink target variable: $target_variable"
  }
  if [[ -L $link_path ]]; then
    captured_target=$(readlink -- "$link_path")
    [[ -n $captured_target ]] || lite_die "symlink has an empty target: $link_path"
    printf -v "$present_variable" '%s' true
    printf -v "$target_variable" '%s' "$captured_target"
  elif [[ -e $link_path ]]; then
    lite_die "$link_path exists but is not a symlink"
  else
    printf -v "$present_variable" '%s' false
    printf -v "$target_variable" '%s' ''
  fi
}

lite_restore_symlink_state() {
  local link_path=$1
  local was_present=$2
  local old_target=${3:-}
  [[ $link_path == "$LITE_ROOT/"* ]] || {
    lite_die "refusing to restore symlink outside $LITE_ROOT"
  }
  case $was_present in
    true)
      [[ -n $old_target ]] || lite_die "cannot restore $link_path without its old target"
      lite_atomic_symlink "$old_target" "$link_path"
      ;;
    false)
      if [[ -e $link_path && ! -L $link_path ]]; then
        lite_die "refusing to remove non-symlink while restoring $link_path"
      fi
      rm -f -- "${link_path}.new" "${link_path}.new.$$" "$link_path" || return
      ;;
    *)
      lite_die "invalid saved symlink state for $link_path: $was_present"
      ;;
  esac
}

lite_verify_nginx_entry() {
  local site=${1:-/etc/nginx/sites-enabled/training-kb}
  local auth_status domain expected_status listener_report probe_path
  local loopback_origin public_origin

  [[ -f $site ]] || lite_die "enabled Nginx entry is not a regular config: $site"
  nginx -t >/dev/null
  expected_status=401
  if grep -Eq 'training-kb-public-mode:[[:space:]]*anonymous' "$site"; then
    expected_status=200
  fi

  if grep -Eq '^[[:space:]]*listen[[:space:]]+127\.0\.0\.1:8088([[:space:]]|;)' "$site"; then
    if awk '$1 == "listen" {value=$2; sub(/;$/, "", value); print value}' "$site" |
      grep -Evqx '127\.0\.0\.1:8088'; then
      lite_die "Quick Tunnel Nginx entry has a listener other than 127.0.0.1:8088"
    fi
    listener_report=$(ss -ltnH | awk '
      $4 ~ /^127\.0\.0\.1:8088$/ {loopback++}
      $4 ~ /(^|:)8088$/ && $4 !~ /^127\.0\.0\.1:8088$/ {public++}
      END {printf "%d %d", loopback, public}
    ')
    read -r loopback_origin public_origin <<< "$listener_report"
    [[ $loopback_origin -ge 1 && $public_origin -eq 0 ]] || {
      lite_die "Quick Tunnel origin is not exclusively bound to 127.0.0.1:8088"
    }
    for probe_path in / /api/health; do
      auth_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --connect-timeout 2 --max-time 10 "http://127.0.0.1:8088${probe_path}")
      [[ $auth_status == "$expected_status" ]] || {
        lite_die "Quick Tunnel origin returned $auth_status at $probe_path, expected $expected_status"
      }
    done
    return
  fi

  if grep -Eq '^[[:space:]]*listen[[:space:]]+([^;[:space:]]*:)?443[[:space:]]+ssl([[:space:]]|;)' "$site"; then
    domain=$(awk '$1 == "server_name" {value=$2; sub(/;$/, "", value); if (value != "_") {print value; exit}}' "$site")
    [[ $domain =~ ^[A-Za-z0-9.-]+$ ]] || lite_die "cannot determine HTTPS Nginx server_name"
    for probe_path in / /api/health; do
      auth_status=$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' \
        --connect-timeout 2 --max-time 10 --resolve "$domain:443:127.0.0.1" \
        "https://${domain}${probe_path}")
      [[ $auth_status == "$expected_status" ]] || {
        lite_die "HTTPS Nginx entry returned $auth_status at $probe_path, expected $expected_status"
      }
    done
    return
  fi

  if grep -Eq '^[[:space:]]*listen[[:space:]]+([^;[:space:]]*:)?80([[:space:]]|;)' "$site"; then
    for probe_path in / /api/health; do
      auth_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
        --connect-timeout 2 --max-time 10 "http://127.0.0.1${probe_path}")
      [[ $auth_status == "$expected_status" ]] || {
        lite_die "HTTP Nginx entry returned $auth_status at $probe_path, expected $expected_status"
      }
    done
    return
  fi

  lite_die "enabled Nginx entry has no supported protected listener"
}

lite_env_value() {
  local env_file=$1
  local key=$2
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$env_file"
}

lite_validate_env_file() {
  local env_file=$1
  local mode owner group
  [[ -f $env_file && ! -L $env_file ]] || lite_die "environment file must be regular: $env_file"
  mode=$(stat -c '%a' "$env_file")
  owner=$(stat -c '%U' "$env_file")
  group=$(stat -c '%G' "$env_file")
  [[ $mode == 600 ]] || lite_die "$env_file must have mode 0600 (found $mode)"
  [[ $owner == root && $group == root ]] || lite_die "$env_file must be root:root"
  awk '
    /^[[:space:]]*($|#)/ { next }
    $0 !~ /^[A-Za-z_][A-Za-z0-9_]*=[^\r\n]*$/ {
      printf "invalid environment line %d in %s\n", NR, FILENAME > "/dev/stderr"
      failed = 1
      next
    }
    {
      key = $0
      sub(/=.*/, "", key)
      if (++seen[key] > 1) {
        printf "duplicate environment key %s in %s\n", key, FILENAME > "/dev/stderr"
        failed = 1
      }
    }
    END { exit failed ? 1 : 0 }
  ' "$env_file" || lite_die "invalid environment file: $env_file"
}

lite_validate_weknora_env_policy() {
  local env_file=$1
  local aes_key jwt_secret
  lite_validate_env_file "$env_file"
  [[ $(lite_env_value "$env_file" SERVER_HOST) == 127.0.0.1 ]] || lite_die "WeKnora must bind 127.0.0.1"
  [[ $(lite_env_value "$env_file" SERVER_PORT) == 8080 ]] || lite_die "WeKnora must use port 8080"
  [[ $(lite_env_value "$env_file" DB_DRIVER) == sqlite ]] || lite_die "WeKnora DB_DRIVER must be sqlite"
  [[ $(lite_env_value "$env_file" RETRIEVE_DRIVER) == sqlite ]] || lite_die "WeKnora RETRIEVE_DRIVER must be sqlite"
  [[ $(lite_env_value "$env_file" STREAM_MANAGER_TYPE) == memory ]] || lite_die "WeKnora STREAM_MANAGER_TYPE must be memory"
  [[ $(lite_env_value "$env_file" WEKNORA_SANDBOX_MODE) == disabled ]] || lite_die "WeKnora sandbox must be disabled"
  [[ $(lite_env_value "$env_file" WEKNORA_WEB_DIR) == "$LITE_ROOT/current/weknora/web" ]] || lite_die "unexpected WeKnora web directory"
  aes_key=$(lite_env_value "$env_file" SYSTEM_AES_KEY)
  jwt_secret=$(lite_env_value "$env_file" JWT_SECRET)
  [[ $aes_key != 00000000000000000000000000000000 ]] || lite_die "SYSTEM_AES_KEY is the all-zero weak default"
  [[ $aes_key != 'weknora-system-aes-key-32bytes!!' ]] || lite_die "SYSTEM_AES_KEY is the official weak example"
  [[ $aes_key =~ ^[0-9a-f]{32}$ ]] || lite_die "SYSTEM_AES_KEY must be exactly 32 generated ASCII bytes"
  [[ $jwt_secret =~ ^[0-9a-f]{96}$ ]] || lite_die "JWT_SECRET must be generated 96-character hex"
  [[ $(lite_env_value "$env_file" CONCURRENCY_POOL_SIZE) == 1 ]] || lite_die "SQLite CONCURRENCY_POOL_SIZE must be 1"
}

lite_validate_training_env_policy() {
  local env_file=$1
  lite_validate_env_file "$env_file"
  [[ $(lite_env_value "$env_file" HOST) == 127.0.0.1 ]] || lite_die "training app must bind 127.0.0.1"
  [[ $(lite_env_value "$env_file" PORT) == 8787 ]] || lite_die "training app must use port 8787"
  [[ $(lite_env_value "$env_file" SILICONFLOW_BASE_URL) == https://api.siliconflow.cn/v1/chat/completions ]] || lite_die "unexpected SiliconFlow endpoint"
  [[ $(lite_env_value "$env_file" SILICONFLOW_MOCK) == 0 ]] || lite_die "production training app must not use mock mode"
  [[ $(lite_env_value "$env_file" WEKNORA_BASE_URL) == http://127.0.0.1:8080 ]] || lite_die "training app must use loopback WeKnora"
  [[ $(lite_env_value "$env_file" WEKNORA_REQUIRED) == 1 ]] || lite_die "WEKNORA_REQUIRED must be 1"
}

lite_wait_http() {
  local url=$1
  local label=$2
  local attempt
  for attempt in $(seq 1 90); do
    if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  printf 'timed out waiting for %s at %s\n' "$label" "$url" >&2
  return 1
}

lite_wait_http_status() {
  local url=$1
  local label=$2
  shift 2
  local attempt status allowed
  for attempt in $(seq 1 90); do
    status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
      --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || true)
    for allowed in "$@"; do
      if [[ $status == "$allowed" ]]; then
        return 0
      fi
    done
    sleep 2
  done
  printf 'timed out waiting for %s at %s (allowed HTTP status: %s)\n' \
    "$label" "$url" "$*" >&2
  return 1
}

lite_service_active() {
  systemctl is-active --quiet "$1"
}

lite_stop_services() {
  systemctl stop "$LITE_TRAINING_SERVICE" "$LITE_WEKNORA_SERVICE"
}

lite_start_services() {
  systemctl start "$LITE_WEKNORA_SERVICE" || return
  lite_wait_http http://127.0.0.1:8080/health WeKnora || return
  systemctl start "$LITE_TRAINING_SERVICE" || return
  # A new installation deliberately starts fail-closed until the scoped
  # WeKnora runtime key and four-KB allow-list have been provisioned.  During
  # that bootstrap phase /api/health returns a structured 503 while the
  # process is healthy and listening.  Strict verification still requires
  # HTTP 200 after the real credentials are installed.
  lite_wait_http_status http://127.0.0.1:8787/api/health "training application" 200 503 || return
}
