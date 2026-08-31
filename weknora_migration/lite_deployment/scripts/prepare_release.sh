#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$script_dir/common.sh"

lite_require_root
lite_load_versions

if [[ $# -lt 1 || $# -gt 2 || $1 != /* ]]; then
  printf 'usage: %s /absolute/path/to/customer-service-ai-training [release-id]\n' "$0" >&2
  exit 2
fi

project_root=$(readlink -f -- "$1")
[[ -d $project_root && ! -L $project_root ]] || lite_die "project root is not a regular directory: $1"
[[ -f $project_root/local_app/server.py ]] || lite_die "missing local_app/server.py"
[[ -f $project_root/local_app/weknora_client.py ]] || lite_die "missing local_app/weknora_client.py"
[[ -d $project_root/local_app/static ]] || lite_die "missing local_app/static"
[[ -d $project_root/knowledge_base ]] || lite_die "missing knowledge_base"

if [[ $# -eq 2 ]]; then
  release_id=$2
else
  project_short=unversioned
  if git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    project_short=$(git -C "$project_root" rev-parse --short=12 HEAD)
  fi
  release_id=$(date -u +%Y%m%d%H%M%S)-$project_short
fi
lite_validate_release_id "$release_id"

release_dir=$LITE_RELEASES/$release_id
[[ ! -e $release_dir && ! -L $release_dir ]] || lite_die "release already exists: $release_dir"

lite_require_commands chown curl flock gcc git go node npm python3 rsync sha256sum sqlite3 systemctl
[[ $(go version | awk '{print $3}') == go${GO_VERSION} ]] || lite_die "Go ${GO_VERSION} is required"
[[ $(node --version) == v${NODE_VERSION} ]] || lite_die "Node.js ${NODE_VERSION} is required"
[[ $(go env CGO_ENABLED) == 1 ]] || lite_die "CGO must be enabled"
sqlite3 :memory: 'CREATE VIRTUAL TABLE probe USING fts5(content);' || lite_die "SQLite FTS5 is unavailable"
lite_validate_weknora_env_policy "$LITE_WEKNORA_ENV"
lite_validate_training_env_policy "$LITE_TRAINING_ENV"

build_root=$(mktemp -d "$LITE_ROOT/.build-${release_id}.XXXXXX")
stage_dir=$LITE_RELEASES/.staging-${release_id}-$$
[[ ! -e $stage_dir && ! -L $stage_dir ]] || lite_die "staging path already exists: $stage_dir"
release_installed=false
activation_transaction=false
# A Quick Tunnel is bound to the training service on an already-public
# installation, so systemd stops it while the application is restarted.
# Preserve the prior intent without making a tunnel a requirement for a
# private/SSH-only deployment.
public_tunnel_service=training-quick-tunnel.service
public_tunnel_was_active=false
if systemctl is-active --quiet "$public_tunnel_service"; then
  public_tunnel_was_active=true
fi

restore_public_tunnel() {
  [[ $public_tunnel_was_active == true ]] || return 0
  systemctl start "$public_tunnel_service" || return
  systemctl is-active --quiet "$public_tunnel_service"
}

cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if [[ ${activation_transaction:-false} == true ]]; then
    lite_stop_services 2>/dev/null || true
    if ! (restore_release_links); then
      printf '%s\n' 'error: interrupted activation could not restore the original current/previous links' >&2
    elif [[ ${old_current_present:-false} == true ]]; then
      if ! recover_prior_release; then
        printf '%s\n' 'error: original links were restored but the prior release did not recover healthy' >&2
      fi
    fi
    if ! restore_public_tunnel; then
      printf '%s\n' 'error: original release recovered but the previously active public tunnel did not restart' >&2
    fi
  fi
  if [[ -n ${build_root:-} && -d $build_root && $build_root == "$LITE_ROOT/.build-"* ]]; then
    rm -rf -- "$build_root"
  fi
  if [[ $release_installed != true && -n ${stage_dir:-} && -d $stage_dir && $stage_dir == "$LITE_RELEASES/.staging-"* ]]; then
    rm -rf -- "$stage_dir"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

weknora_source=$build_root/WeKnora
source_archive=${WEKNORA_SOURCE_ARCHIVE:-/var/cache/training-kb/WeKnora-${WEKNORA_TAG}.tar.gz}
if [[ -f $source_archive ]]; then
  [[ ! -L $source_archive ]] || lite_die "cached WeKnora source archive must not be a symlink"
  [[ $(stat -c '%U:%G' "$source_archive") == root:root ]] || lite_die "cached WeKnora source archive must be root:root"
  [[ $(stat -c '%a' "$source_archive") == 600 ]] || lite_die "cached WeKnora source archive must have mode 0600"
  printf '%s  %s\n' "$WEKNORA_SOURCE_ARCHIVE_SHA256" "$source_archive" | \
    sha256sum --check --status || lite_die "cached WeKnora source archive checksum mismatch"
  python3 - "$source_archive" <<'PY'
import pathlib
import sys
import tarfile

archive = pathlib.Path(sys.argv[1])
with tarfile.open(archive, "r:gz") as handle:
    members = handle.getmembers()
    if not members:
        raise SystemExit("cached WeKnora source archive is empty")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) < 2
            or path.parts[0] != "WeKnora"
            or path.parts[1] != ".git"
            or not (member.isdir() or member.isfile())
        ):
            raise SystemExit(f"unsafe member in cached WeKnora source archive: {member.name}")
PY
  tar --no-same-owner --no-same-permissions -xzf "$source_archive" -C "$build_root"
  [[ -d $weknora_source/.git ]] || lite_die "cached WeKnora source archive is incomplete"
  if [[ ! -f $weknora_source/go.mod ]]; then
    git -C "$weknora_source" reset --hard --quiet HEAD
  fi
  git -C "$weknora_source" clean -ffdqx
else
  git clone --quiet --depth 1 --branch "$WEKNORA_TAG" "$WEKNORA_REPOSITORY" "$weknora_source"
fi
actual_commit=$(git -C "$weknora_source" rev-parse HEAD)
[[ $actual_commit == "$WEKNORA_COMMIT" ]] || lite_die "the $WEKNORA_TAG tag resolved to unexpected commit $actual_commit"
git -C "$weknora_source" diff --quiet --exit-code || lite_die "upstream checkout has tracked modifications"
git -C "$weknora_source" diff --cached --quiet --exit-code || lite_die "upstream checkout has staged modifications"
[[ -z $(git -C "$weknora_source" status --porcelain --untracked-files=all) ]] || lite_die "upstream checkout has untracked files"
grep -qx 'go 1.26.0' "$weknora_source/go.mod" || lite_die "upstream go.mod no longer requires Go 1.26.0"

# v0.7.2 shipped an incomplete Lite SQLite migration set (official issue
# Tencent/WeKnora#2158). Backport only the official merged SQLite migrations
# from commit 71fe7f31... so the API and binary remain pinned to v0.7.2 while
# fresh Lite databases receive the schema required by that binary.
sqlite_patch_root=$LITE_DEPLOYMENT_DIR/upstream_patches/sqlite-$WEKNORA_SQLITE_PATCH_COMMIT
sqlite_patch_dir=$sqlite_patch_root/migrations/sqlite
[[ -d $sqlite_patch_dir && ! -L $sqlite_patch_dir ]] || lite_die "missing official SQLite migration patch"
[[ -f $sqlite_patch_root/SHA256SUMS && ! -L $sqlite_patch_root/SHA256SUMS ]] || {
  lite_die "missing SQLite migration patch checksums"
}
(
  cd "$sqlite_patch_root"
  sha256sum --check --strict --status SHA256SUMS
) || lite_die "SQLite migration patch checksum mismatch"
patch_file_count=$(find "$sqlite_patch_dir" -maxdepth 1 -type f -name '*.sql' | wc -l)
[[ $patch_file_count -eq 18 ]] || lite_die "SQLite migration patch must contain exactly 18 SQL files"
unexpected_patch_node=$(find "$sqlite_patch_root" ! -type d ! -type f -print -quit)
[[ -z $unexpected_patch_node ]] || lite_die "SQLite migration patch contains a symlink or special file"
find "$sqlite_patch_dir" -maxdepth 1 -type f -name '*.sql' -exec \
  install -o root -g root -m 0644 -t "$weknora_source/migrations/sqlite" -- {} +
for migration_version in $(seq -w 0 "$WEKNORA_SQLITE_SCHEMA_VERSION"); do
  migration_prefix=$(printf '%06d' "$((10#$migration_version))")
  [[ $(find "$weknora_source/migrations/sqlite" -maxdepth 1 -type f \
    -name "${migration_prefix}_*.up.sql" | wc -l) -eq 1 ]] || {
    lite_die "SQLite migration ${migration_prefix} up file is missing or duplicated"
  }
  [[ $(find "$weknora_source/migrations/sqlite" -maxdepth 1 -type f \
    -name "${migration_prefix}_*.down.sql" | wc -l) -eq 1 ]] || {
    lite_die "SQLite migration ${migration_prefix} down file is missing or duplicated"
  }
done
[[ $(find "$weknora_source/migrations/sqlite" -maxdepth 1 -type f -name '*.sql' | wc -l) -eq 24 ]] || {
  lite_die "patched SQLite migration set must contain exactly 24 SQL files"
}

printf '%s\n' "building WeKnora frontend with Node.js $(node --version)"
(
  cd "$weknora_source/frontend"
  NODE_OPTIONS=--max-old-space-size=3072 \
    npm_config_registry=https://registry.npmmirror.com \
    npm ci --no-audit --no-fund
  NODE_OPTIONS=--max-old-space-size=3072 npm run build
)
[[ -f $weknora_source/frontend/dist/index.html ]] || lite_die "WeKnora frontend build produced no index.html"
install -d -m 0755 "$weknora_source/web"
cp -a "$weknora_source/frontend/dist/." "$weknora_source/web/"

printf '%s\n' "building WeKnora Lite with $(go version | awk '{print $3}') and CGO/sqlite_fts5"
for cache_dir in \
  /var/cache/training-kb/go \
  /var/cache/training-kb/go-mod \
  /var/cache/training-kb/go-build; do
  [[ ! -L $cache_dir ]] || lite_die "build cache must not be a symlink: $cache_dir"
  install -d -o root -g root -m 0755 "$cache_dir"
  [[ $(stat -c '%U:%G:%a' "$cache_dir") == root:root:755 ]] || {
    lite_die "invalid build cache ownership or mode: $cache_dir"
  }
done
(
  cd "$weknora_source"
  export EDITION=lite
  export CGO_ENABLED=1
  export CGO_CFLAGS=-Wno-deprecated-declarations
  export GOMAXPROCS=2
  export GOPATH=/var/cache/training-kb/go
  export GOMODCACHE=/var/cache/training-kb/go-mod
  export GOCACHE=/var/cache/training-kb/go-build
  export GOPROXY=https://goproxy.cn,https://proxy.golang.org,direct
  ldflags=$(./scripts/get_version.sh ldflags)
  go build -p 2 -trimpath -tags sqlite_fts5 \
    -ldflags="-w -s $ldflags -X 'google.golang.org/protobuf/reflect/protoregistry.conflictPolicy=warn'" \
    -o WeKnora-lite ./cmd/server
)
[[ -x $weknora_source/WeKnora-lite ]] || lite_die "WeKnora Lite binary build failed"

install -d -m 0755 "$stage_dir/weknora/web" "$stage_dir/training-app"
install -o root -g root -m 0755 "$weknora_source/WeKnora-lite" "$stage_dir/weknora/WeKnora-lite"
cp -a "$weknora_source/web/." "$stage_dir/weknora/web/"
cp -a "$weknora_source/config" "$stage_dir/weknora/config"
install -d -m 0755 "$stage_dir/weknora/migrations"
cp -a "$weknora_source/migrations/sqlite" "$stage_dir/weknora/migrations/sqlite"
install -o root -g root -m 0644 "$weknora_source/LICENSE" "$stage_dir/weknora/LICENSE"

jieba_dict_source=/var/cache/training-kb/go-mod/github.com/yanyiwu/gojieba@v1.4.7/deps/cppjieba/dict
[[ -d $jieba_dict_source ]] || lite_die "gojieba dictionary source is missing"
install -d -o root -g root -m 0755 "$stage_dir/weknora/jieba-dict"
for dict_name in jieba.dict.utf8 hmm_model.utf8 user.dict.utf8 idf.utf8 stop_words.utf8; do
  [[ -f $jieba_dict_source/$dict_name && ! -L $jieba_dict_source/$dict_name ]] || {
    lite_die "required gojieba dictionary is missing: $dict_name"
  }
  install -o root -g root -m 0644 \
    "$jieba_dict_source/$dict_name" "$stage_dir/weknora/jieba-dict/$dict_name"
done

rsync -a --exclude '__pycache__/' --exclude '*.py[co]' --exclude '.env' \
  "$project_root/local_app" "$stage_dir/training-app/"
rsync -a --exclude '__pycache__/' --exclude '*.py[co]' \
  "$project_root/knowledge_base" "$stage_dir/training-app/"

python3 - "$stage_dir/training-app" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
for source in root.rglob("*.py"):
    compile(source.read_bytes(), str(source), "exec")
PY

unexpected_node=$(find "$stage_dir" ! -type d ! -type f -print -quit)
[[ -z $unexpected_node ]] || lite_die "release contains a symlink or special file: $unexpected_node"

project_commit=unversioned
project_dirty=unknown
if git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  project_commit=$(git -C "$project_root" rev-parse HEAD)
  project_dirty=false
  if ! git -C "$project_root" diff --quiet --exit-code || \
     ! git -C "$project_root" diff --cached --quiet --exit-code || \
     [[ -n $(git -C "$project_root" ls-files --others --exclude-standard) ]]; then
    project_dirty=true
  fi
fi
build_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
{
  printf 'RELEASE_ID=%s\n' "$release_id"
  printf 'BUILD_TIME_UTC=%s\n' "$build_time"
  printf 'WEKNORA_TAG=%s\n' "$WEKNORA_TAG"
  printf 'WEKNORA_COMMIT=%s\n' "$WEKNORA_COMMIT"
  printf 'WEKNORA_SQLITE_PATCH_COMMIT=%s\n' "$WEKNORA_SQLITE_PATCH_COMMIT"
  printf 'WEKNORA_SQLITE_SCHEMA_VERSION=%s\n' "$WEKNORA_SQLITE_SCHEMA_VERSION"
  printf 'GO_VERSION=%s\n' "$GO_VERSION"
  printf 'NODE_VERSION=%s\n' "$NODE_VERSION"
  printf 'PROJECT_COMMIT=%s\n' "$project_commit"
  printf 'PROJECT_DIRTY=%s\n' "$project_dirty"
} > "$stage_dir/RELEASE_MANIFEST.env"

chown -R root:root "$stage_dir"
find "$stage_dir" -type d -exec chmod 0755 {} +
find "$stage_dir" -type f -exec chmod 0644 {} +
chmod 0755 "$stage_dir/weknora/WeKnora-lite"
(
  cd "$stage_dir"
  find RELEASE_MANIFEST.env training-app weknora -type f -print0 |
    LC_ALL=C sort -z |
    xargs -0 sha256sum > RELEASE.sha256
  sha256sum --check --status RELEASE.sha256
)

# The long npm/go build stays outside the lock. Recheck the destination under
# the shared release lock, then require GNU mv's no-directory-merging mode.
lite_acquire_release_lock
[[ ! -e $release_dir && ! -L $release_dir ]] || lite_die "release already exists: $release_dir"
mv -T -- "$stage_dir" "$release_dir"
release_installed=true
lite_assert_release_dir "$release_dir"

old_current_present=false
old_current_link=
old_previous_present=false
old_previous_link=
lite_capture_symlink_state "$LITE_CURRENT" old_current_present old_current_link
lite_capture_symlink_state "$LITE_PREVIOUS" old_previous_present old_previous_link

if [[ $old_current_present == true ]]; then
  old_resolved=$(readlink -f -- "$LITE_CURRENT")
  lite_assert_release_dir "$old_resolved"
fi
if [[ $old_previous_present == true ]]; then
  lite_assert_release_dir "$(readlink -f -- "$LITE_PREVIOUS")"
fi

activate_release_links() {
  if [[ $old_current_present == true ]]; then
    lite_atomic_symlink "$old_current_link" "$LITE_PREVIOUS" || return
  fi
  lite_atomic_symlink "releases/$release_id" "$LITE_CURRENT" || return
}

restore_release_links() {
  lite_restore_symlink_state "$LITE_CURRENT" "$old_current_present" "$old_current_link" || return
  lite_restore_symlink_state "$LITE_PREVIOUS" "$old_previous_present" "$old_previous_link" || return
}

recover_prior_release() {
  [[ $old_current_present == true ]] || return 0
  lite_start_services || return
  "$script_dir/verify.sh" --basic || return
  restore_public_tunnel || return
}

activation_ok=false
activation_transaction=true
if activate_release_links && lite_stop_services 2>/dev/null && lite_start_services && \
  "$script_dir/verify.sh" --basic && restore_public_tunnel; then
  activation_ok=true
  activation_transaction=false
fi

if [[ $activation_ok != true ]]; then
  lite_stop_services 2>/dev/null || true
  restore_release_links || lite_die "new release failed and the original current/previous links could not be restored"
  recovery_ok=true
  if ! recover_prior_release; then
    recovery_ok=false
  fi
  activation_transaction=false
  [[ $recovery_ok == true ]] || {
    lite_die "new release failed; original links were restored, but the prior release failed basic recovery verification"
  }
  lite_die "new release failed verification; the original current and previous links were restored"
fi

printf '%s\n' "release activated: $release_dir"
printf '%s\n' "WeKnora: 127.0.0.1:8080 only; training app: 127.0.0.1:8787 only"
printf '%s\n' "configure /etc/training-kb/training.env, import the knowledge bundle, then run verify.sh --strict"
