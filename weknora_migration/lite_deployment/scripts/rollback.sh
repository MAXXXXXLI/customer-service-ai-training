#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=common.sh
source "$script_dir/common.sh"

lite_require_root

rollback_transaction=false
rollback_cleanup() {
  local status=$?
  trap - EXIT HUP INT TERM
  if [[ ${rollback_transaction:-false} == true ]]; then
    lite_stop_services 2>/dev/null || true
    if ! (restore_rollback_links); then
      printf '%s\n' 'error: interrupted rollback could not restore the original current/previous links' >&2
    else
      if ! recover_original_release; then
        printf '%s\n' 'error: original links were restored but the original release did not recover healthy' >&2
      fi
    fi
  fi
  exit "$status"
}
trap rollback_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

make_backup=true
target_id=
while [[ $# -gt 0 ]]; do
  case $1 in
    --no-backup)
      make_backup=false
      shift
      ;;
    --help|-h)
      printf 'usage: %s [--no-backup] [release-id]\n' "$0"
      exit 0
      ;;
    -* )
      printf 'unknown option: %s\n' "$1" >&2
      exit 2
      ;;
    *)
      [[ -z $target_id ]] || {
        printf 'only one release id may be supplied\n' >&2
        exit 2
      }
      target_id=$1
      shift
      ;;
  esac
done

lite_require_commands flock
lite_acquire_release_lock

[[ -L $LITE_CURRENT ]] || lite_die "no current release symlink exists"
old_current_present=false
old_current_link=
old_previous_present=false
old_previous_link=
lite_capture_symlink_state "$LITE_CURRENT" old_current_present old_current_link
[[ $old_current_present == true ]] || lite_die "no current release symlink exists"
old_current=$(readlink -f -- "$LITE_CURRENT")
lite_assert_release_dir "$old_current"

lite_capture_symlink_state "$LITE_PREVIOUS" old_previous_present old_previous_link
if [[ $old_previous_present == true ]]; then
  lite_assert_release_dir "$(readlink -f -- "$LITE_PREVIOUS")"
fi

if [[ -n $target_id ]]; then
  lite_validate_release_id "$target_id"
  target=$LITE_RELEASES/$target_id
else
  [[ -L $LITE_PREVIOUS ]] || lite_die "no previous release is recorded; supply a release id"
  target=$(readlink -f -- "$LITE_PREVIOUS")
  target_id=$(basename -- "$target")
fi
lite_validate_release_id "$target_id"
lite_assert_release_dir "$target"
[[ $(readlink -f -- "$target") == "$(readlink -f -- "$LITE_RELEASES/$target_id")" ]] || {
  lite_die "rollback target is not a direct release directory: $target"
}
[[ $(readlink -f -- "$target") != "$old_current" ]] || lite_die "target release is already current"

if [[ $make_backup == true ]]; then
  "$script_dir/backup.sh"
fi

activate_rollback_links() {
  lite_atomic_symlink "releases/$target_id" "$LITE_CURRENT" || return
  lite_atomic_symlink "$old_current_link" "$LITE_PREVIOUS" || return
}

restore_rollback_links() {
  lite_restore_symlink_state "$LITE_CURRENT" "$old_current_present" "$old_current_link" || return
  lite_restore_symlink_state "$LITE_PREVIOUS" "$old_previous_present" "$old_previous_link" || return
}

recover_original_release() {
  lite_start_services || return
  "$script_dir/verify.sh" --basic || return
}

rollback_ok=false
rollback_transaction=true
lite_stop_services
if activate_rollback_links && lite_start_services && "$script_dir/verify.sh" --basic; then
  rollback_ok=true
  rollback_transaction=false
fi

if [[ $rollback_ok != true ]]; then
  lite_stop_services 2>/dev/null || true
  restore_rollback_links || lite_die "rollback failed and the original current/previous links could not be restored"
  recovery_ok=true
  if ! recover_original_release; then
    recovery_ok=false
  fi
  rollback_transaction=false
  [[ $recovery_ok == true ]] || {
    lite_die "rollback failed; original links were restored, but the original release failed basic recovery verification"
  }
  lite_die "rollback target failed verification; the original current and previous links were restored"
fi

printf '%s\n' "rollback complete: $target_id"
printf '%s\n' "data was preserved; the automatically created backup can be restored separately if required"
