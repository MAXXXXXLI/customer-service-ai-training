#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$script_dir/common.sh"

lite_require_root
lite_require_commands cp curl flock readlink sha256sum systemctl tar

backup_dir=$LITE_BACKUPS
if [[ $# -eq 1 && $1 == /* ]]; then
  backup_dir=$1
elif [[ $# -ne 0 ]]; then
  printf 'usage: %s [/absolute/backup/directory]\n' "$0" >&2
  exit 2
fi

lite_acquire_release_lock

if [[ -e $backup_dir ]]; then
  [[ -d $backup_dir && ! -L $backup_dir ]] || lite_die "backup destination must be a regular directory"
else
  install -d -o root -g root -m 0700 "$backup_dir"
fi
chmod 0700 "$backup_dir"

[[ -L $LITE_CURRENT ]] || lite_die "no current release is installed"
current_release=$(readlink -f -- "$LITE_CURRENT")
lite_assert_release_dir "$current_release"
lite_validate_env_file "$LITE_WEKNORA_ENV"
lite_validate_env_file "$LITE_TRAINING_ENV"

weknora_was_active=false
training_was_active=false
tunnel_was_active=false
lite_service_active "$LITE_WEKNORA_SERVICE" && weknora_was_active=true
lite_service_active "$LITE_TRAINING_SERVICE" && training_was_active=true
lite_service_active training-quick-tunnel.service && tunnel_was_active=true

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
release_id=$(basename -- "$current_release")
archive_name=training-kb-${timestamp}-${release_id}.tar.gz
archive=$backup_dir/$archive_name
partial=$backup_dir/.${archive_name}.partial
[[ ! -e $archive && ! -L $archive && ! -e $archive.sha256 && ! -L $archive.sha256 ]] || {
  lite_die "backup output already exists: $archive"
}
stage=$(mktemp -d "$backup_dir/.backup-stage.XXXXXX")
services_restored=false

restore_services() {
  local failed=false
  if [[ $services_restored == true ]]; then
    return 0
  fi
  if [[ $weknora_was_active == true ]]; then
    if ! systemctl start "$LITE_WEKNORA_SERVICE"; then
      failed=true
    elif ! lite_wait_http http://127.0.0.1:8080/health WeKnora; then
      failed=true
    fi
  fi
  if [[ $training_was_active == true ]]; then
    if ! systemctl start "$LITE_TRAINING_SERVICE"; then
      failed=true
    elif ! lite_wait_http_status http://127.0.0.1:8787/api/health \
      "training application" 200 503; then
      failed=true
    fi
  fi
  if [[ $tunnel_was_active == true ]]; then
    rm -f -- /var/lib/training-tunnel/public-url.txt
    if ! systemctl start training-quick-tunnel.service; then
      failed=true
    else
      public_url=
      for _ in $(seq 1 60); do
        if [[ -s /var/lib/training-tunnel/public-url.txt ]]; then
          public_url=$(cat /var/lib/training-tunnel/public-url.txt)
          if [[ $public_url =~ ^https://[a-z0-9-]+\.trycloudflare\.com$ ]] \
            && curl -fsS --max-time 10 "$public_url/api/health" >/dev/null 2>&1; then
            break
          fi
        fi
        sleep 2
      done
      if [[ ! $public_url =~ ^https://[a-z0-9-]+\.trycloudflare\.com$ ]] \
        || ! curl -fsS --max-time 10 "$public_url/api/health" >/dev/null 2>&1; then
        failed=true
      fi
    fi
  fi
  [[ $failed == false ]] || return 1
  services_restored=true
}

cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if ! restore_services; then
    printf '%s\n' 'error: backup cleanup could not restore the original service state' >&2
    status=1
  fi
  if [[ -d ${stage:-} && $stage == "$backup_dir/.backup-stage."* ]]; then
    rm -rf -- "$stage"
  fi
  rm -f -- "$partial"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

systemctl stop training-quick-tunnel.service "$LITE_TRAINING_SERVICE" "$LITE_WEKNORA_SERVICE"

install -d -m 0700 "$stage/state" "$stage/etc" "$stage/systemd" "$stage/nginx" "$stage/release-metadata"
cp -a "$LITE_STATE/." "$stage/state/"
install -o root -g root -m 0600 "$LITE_WEKNORA_ENV" "$stage/etc/weknora.env"
install -o root -g root -m 0600 "$LITE_TRAINING_ENV" "$stage/etc/training.env"
install -o root -g root -m 0644 /etc/systemd/system/weknora-lite.service "$stage/systemd/weknora-lite.service"
install -o root -g root -m 0644 /etc/systemd/system/training-app.service "$stage/systemd/training-app.service"
install -o root -g root -m 0644 "$current_release/RELEASE_MANIFEST.env" "$stage/release-metadata/RELEASE_MANIFEST.env"
install -o root -g root -m 0644 "$current_release/RELEASE.sha256" "$stage/release-metadata/RELEASE.sha256"
[[ -f /etc/nginx/sites-available/training-kb ]] && cp -a /etc/nginx/sites-available/training-kb "$stage/nginx/training-kb.conf"
[[ -f /etc/nginx/training-kb.htpasswd ]] && install -o root -g root -m 0600 /etc/nginx/training-kb.htpasswd "$stage/nginx/training-kb.htpasswd"
{
  printf 'BACKUP_TIME_UTC=%s\n' "$timestamp"
  printf 'RELEASE_ID=%s\n' "$release_id"
  printf 'RELEASE_SHA256=%s\n' "$(sha256sum "$current_release/RELEASE.sha256" | awk '{print $1}')"
  printf 'WEKNORA_WAS_ACTIVE=%s\n' "$weknora_was_active"
  printf 'TRAINING_WAS_ACTIVE=%s\n' "$training_was_active"
  printf 'TUNNEL_WAS_ACTIVE=%s\n' "$tunnel_was_active"
} > "$stage/BACKUP_MANIFEST.env"

tar -C "$stage" -czf "$partial" .
chmod 0600 "$partial"
mv -- "$partial" "$archive"
(
  cd "$backup_dir"
  sha256sum "$archive_name" > "$archive_name.sha256"
)
chmod 0600 "$archive.sha256"

restore_services || lite_die "backup was written, but the original service state failed recovery verification"

printf '%s\n' "backup created: $archive"
printf '%s\n' "checksum: $archive.sha256"
