#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$script_dir/common.sh"

lite_require_root
lite_load_versions

[[ -r /etc/os-release ]] || lite_die "cannot identify the operating system"
# shellcheck disable=SC1091
source /etc/os-release
[[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 22.04 ]] || {
  lite_die "this deployment is pinned to Ubuntu 22.04 LTS"
}

case $(uname -m) in
  x86_64)
    go_arch=amd64
    node_arch=x64
    go_checksum=$GO_LINUX_AMD64_SHA256
    node_checksum=$NODE_LINUX_AMD64_SHA256
    ;;
  aarch64|arm64)
    go_arch=arm64
    node_arch=arm64
    go_checksum=$GO_LINUX_ARM64_SHA256
    node_checksum=$NODE_LINUX_ARM64_SHA256
    ;;
  *)
    lite_die "unsupported CPU architecture: $(uname -m)"
    ;;
esac

export DEBIAN_FRONTEND=noninteractive
public_entry_was_enabled=false
[[ -L /etc/nginx/sites-enabled/training-kb ]] && public_entry_was_enabled=true
apt-get update
apt-get install -y --no-install-recommends \
  apache2-utils build-essential ca-certificates curl git iproute2 jq \
  libsqlite3-dev nginx openssl pkg-config python3 rsync sqlite3 \
  tar ufw xz-utils
if [[ $public_entry_was_enabled != true ]]; then
  systemctl disable --now nginx >/dev/null 2>&1 || true
fi

lite_require_commands \
  blkid curl fallocate gcc getent git groupadd mkswap nginx openssl \
  id pkg-config python3 rsync sha256sum sqlite3 stat swapon sysctl systemctl \
  tar useradd

install -d -m 0755 /opt/toolchains

download_verified_archive() {
  local output=$1
  local expected_checksum=$2
  shift 2
  local url

  for url in "$@"; do
    if curl --fail --location --silent --show-error --retry 2 \
      --connect-timeout 15 --max-time 600 --output "$output" "$url" && \
      printf '%s  %s\n' "$expected_checksum" "$output" | sha256sum --check --status; then
        return 0
    fi
    rm -f -- "$output"
  done

  return 1
}

install_go() {
  local archive_name=go${GO_VERSION}.linux-${go_arch}.tar.gz
  local go_root=/opt/toolchains/go${GO_VERSION}
  local staging archive actual_version

  if [[ -e $go_root ]]; then
    [[ -x $go_root/bin/go ]] || lite_die "incomplete existing Go toolchain: $go_root"
  else
    staging=$(mktemp -d /opt/toolchains/.go-install.XXXXXX)
    archive=$staging/$archive_name
    download_verified_archive "$archive" "$go_checksum" \
      "https://mirrors.aliyun.com/golang/${archive_name}" \
      "https://go.dev/dl/${archive_name}" || {
      rm -rf -- "$staging"
      lite_die "unable to download Go archive"
    }
    printf '%s  %s\n' "$go_checksum" "$archive" | sha256sum --check --status || {
      rm -rf -- "$staging"
      lite_die "Go archive checksum mismatch"
    }
    tar -xzf "$archive" -C "$staging"
    [[ -x $staging/go/bin/go ]] || {
      rm -rf -- "$staging"
      lite_die "downloaded Go archive is incomplete"
    }
    mv -- "$staging/go" "$go_root"
    rm -rf -- "$staging"
  fi

  ln -sfn -- "$go_root/bin/go" /usr/local/bin/go
  ln -sfn -- "$go_root/bin/gofmt" /usr/local/bin/gofmt
  actual_version=$(/usr/local/bin/go version | awk '{print $3}')
  [[ $actual_version == go${GO_VERSION} ]] || lite_die "Go validation failed: $actual_version"
}

install_node() {
  local archive_name=node-v${NODE_VERSION}-linux-${node_arch}.tar.xz
  local node_root=/opt/toolchains/node-v${NODE_VERSION}-linux-${node_arch}
  local staging archive actual_version binary_name

  if [[ -e $node_root ]]; then
    [[ -x $node_root/bin/node ]] || lite_die "incomplete existing Node.js toolchain: $node_root"
  else
    staging=$(mktemp -d /opt/toolchains/.node-install.XXXXXX)
    archive=$staging/$archive_name
    download_verified_archive "$archive" "$node_checksum" \
      "https://mirrors.aliyun.com/nodejs-release/v${NODE_VERSION}/${archive_name}" \
      "https://nodejs.org/dist/v${NODE_VERSION}/${archive_name}" || {
      rm -rf -- "$staging"
      lite_die "unable to download Node.js archive"
    }
    printf '%s  %s\n' "$node_checksum" "$archive" | sha256sum --check --status || {
      rm -rf -- "$staging"
      lite_die "Node.js archive checksum mismatch"
    }
    install -d -m 0755 "$staging/root"
    tar -xJf "$archive" --strip-components=1 -C "$staging/root"
    [[ -x $staging/root/bin/node ]] || {
      rm -rf -- "$staging"
      lite_die "downloaded Node.js archive is incomplete"
    }
    mv -- "$staging/root" "$node_root"
    rm -rf -- "$staging"
  fi

  for binary_name in node npm npx corepack; do
    [[ -e $node_root/bin/$binary_name ]] && ln -sfn -- "$node_root/bin/$binary_name" "/usr/local/bin/$binary_name"
  done
  actual_version=$(/usr/local/bin/node --version)
  [[ $actual_version == v${NODE_VERSION} ]] || lite_die "Node.js validation failed: $actual_version"
  /usr/local/bin/npm --version >/dev/null
}

ensure_swap() {
  local swap_path=/swapfile
  local expected_size=8589934592
  local swap_type

  if [[ ! -e $swap_path ]]; then
    fallocate -l 8G "$swap_path"
    chmod 0600 "$swap_path"
    mkswap "$swap_path" >/dev/null
  else
    [[ -f $swap_path && ! -L $swap_path ]] || lite_die "$swap_path must be a regular file"
    [[ $(stat -c '%s' "$swap_path") -eq $expected_size ]] || lite_die "$swap_path exists but is not exactly 8 GiB"
    [[ $(stat -c '%a' "$swap_path") == 600 ]] || chmod 0600 "$swap_path"
    swap_type=$(blkid -o value -s TYPE "$swap_path" 2>/dev/null || true)
    [[ $swap_type == swap ]] || lite_die "$swap_path exists but is not initialized as swap"
  fi

  if ! swapon --noheadings --show=NAME | awk '$1 == "/swapfile" {found=1} END {exit !found}'; then
    swapon "$swap_path"
  fi
  if ! awk '$1 == "/swapfile" {found=1} END {exit !found}' /etc/fstab; then
    printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
  fi
  printf 'vm.swappiness=10\n' > /etc/sysctl.d/99-training-kb.conf
  sysctl --system >/dev/null
}

ensure_users_and_directories() {
  local account passwd_name passwd_uid passwd_home passwd_shell primary_group
  for account in weknora-lite training-app; do
    if ! getent group "$account" >/dev/null; then
      groupadd --system "$account"
    fi
    if ! getent passwd "$account" >/dev/null; then
      useradd --system --gid "$account" --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin "$account"
      continue
    fi

    IFS=: read -r passwd_name _ passwd_uid _ _ passwd_home passwd_shell <<< "$(getent passwd "$account")"
    primary_group=$(id -gn "$account")
    [[ $passwd_name == "$account" && $passwd_uid =~ ^[0-9]+$ && $passwd_uid -lt 1000 ]] || {
      lite_die "existing $account identity is not a system account"
    }
    [[ $primary_group == "$account" && $passwd_home == /nonexistent && $passwd_shell == /usr/sbin/nologin ]] || {
      lite_die "existing $account identity does not match the dedicated service-user policy"
    }
  done

  install -d -m 0755 "$LITE_ROOT" "$LITE_RELEASES"
  install -d -m 0700 "$LITE_ETC" "$LITE_BACKUPS"
  install -d -o weknora-lite -g weknora-lite -m 0700 "$LITE_STATE" "$LITE_STATE/files"
}

ensure_environment_files() {
  local temporary aes_key jwt_secret
  [[ ! -L $LITE_WEKNORA_ENV ]] || lite_die "refusing symlink environment file: $LITE_WEKNORA_ENV"
  [[ ! -L $LITE_TRAINING_ENV ]] || lite_die "refusing symlink environment file: $LITE_TRAINING_ENV"
  if [[ ! -e $LITE_WEKNORA_ENV ]]; then
    aes_key=$(openssl rand -hex 16)
    jwt_secret=$(openssl rand -hex 48)
    temporary=$(mktemp "$LITE_ETC/.weknora.env.XXXXXX")
    {
      printf 'GIN_MODE=release\n'
      printf 'LOG_LEVEL=info\n'
      printf 'TZ=Asia/Shanghai\n'
      printf 'SERVER_HOST=127.0.0.1\n'
      printf 'SERVER_PORT=8080\n'
      printf 'DB_DRIVER=sqlite\n'
      printf 'DB_PATH=%s/weknora.db\n' "$LITE_STATE"
      printf 'RETRIEVE_DRIVER=sqlite\n'
      printf 'STORAGE_TYPE=local\n'
      printf 'LOCAL_STORAGE_BASE_DIR=%s/files\n' "$LITE_STATE"
      printf 'STREAM_MANAGER_TYPE=memory\n'
      printf 'SYSTEM_AES_KEY=%s\n' "$aes_key"
      printf 'JWT_SECRET=%s\n' "$jwt_secret"
      printf 'NEO4J_ENABLE=false\n'
      printf 'WEKNORA_SANDBOX_MODE=disabled\n'
      printf 'ENABLE_GRAPH_RAG=false\n'
      printf 'DISABLE_REGISTRATION=false\n'
      printf 'CONCURRENCY_POOL_SIZE=1\n'
      printf 'WEKNORA_WEB_DIR=%s/current/weknora/web\n' "$LITE_ROOT"
    } > "$temporary"
    chmod 0600 "$temporary"
    chown root:root "$temporary"
    mv -- "$temporary" "$LITE_WEKNORA_ENV"
    unset aes_key jwt_secret
  fi

  if [[ ! -e $LITE_TRAINING_ENV ]]; then
    install -o root -g root -m 0600 "$LITE_DEPLOYMENT_DIR/templates/training.env.example" "$LITE_TRAINING_ENV"
  fi
  lite_validate_weknora_env_policy "$LITE_WEKNORA_ENV"
  lite_validate_training_env_policy "$LITE_TRAINING_ENV"
}

validate_native_dependencies() {
  local c_probe
  local -a sqlite_flags
  [[ $(go version | awk '{print $3}') == go${GO_VERSION} ]] || lite_die "Go ${GO_VERSION} is not active"
  [[ $(node --version) == v${NODE_VERSION} ]] || lite_die "Node.js ${NODE_VERSION} is not active"
  [[ $(go env CGO_ENABLED) == 1 ]] || lite_die "the Go toolchain reports CGO_ENABLED=0"
  pkg-config --exists sqlite3 || lite_die "pkg-config cannot find sqlite3"
  sqlite3 :memory: 'CREATE VIRTUAL TABLE probe USING fts5(content);' || lite_die "SQLite FTS5 is unavailable"
  c_probe=$(mktemp /tmp/training-kb-cgo.XXXXXX)
  read -r -a sqlite_flags <<< "$(pkg-config --cflags --libs sqlite3)"
  printf '#include <sqlite3.h>\nint main(void){return sqlite3_libversion_number()<1;}\n' |
    gcc -x c - -o "$c_probe" "${sqlite_flags[@]}"
  "$c_probe"
  rm -f -- "$c_probe"
}

install_go
install_node
ensure_swap
ensure_users_and_directories
ensure_environment_files
validate_native_dependencies

install -o root -g root -m 0644 "$LITE_DEPLOYMENT_DIR/systemd/weknora-lite.service" /etc/systemd/system/weknora-lite.service
install -o root -g root -m 0644 "$LITE_DEPLOYMENT_DIR/systemd/training-app.service" /etc/systemd/system/training-app.service
install -o root -g root -m 0644 "$LITE_DEPLOYMENT_DIR/nginx/training-kb.conf.template" /etc/nginx/sites-available/training-kb
systemctl daemon-reload
systemctl enable "$LITE_WEKNORA_SERVICE" "$LITE_TRAINING_SERVICE" >/dev/null
if [[ $public_entry_was_enabled == true ]]; then
  nginx -t
  systemctl reload nginx
fi

printf '%s\n' "host prepared without exposing WeKnora"
printf '%s\n' "Go $(go version | awk '{print $3}'), Node.js $(node --version), SQLite $(sqlite3 --version | awk '{print $1}'), 8 GiB swap"
printf '%s\n' "next: sudo $LITE_SCRIPT_DIR/prepare_release.sh /absolute/path/to/customer-service-ai-training"
