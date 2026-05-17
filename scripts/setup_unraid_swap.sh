#!/usr/bin/env bash
# Create a swap file on Unraid (or any Linux) and print lines to add to /boot/config/go for persistence.
# Prefer XFS cache disk (/mnt/cache) over BTRFS user shares for swap I/O.
#
# Usage:
#   SWAP_SIZE_GB=16 SWAPFILE=/mnt/cache/.aginfo_swap.img bash scripts/setup_unraid_swap.sh
#   # then append the printed swapon line to /boot/config/go on Unraid.
set -euo pipefail

SIZE_GB="${SWAP_SIZE_GB:-16}"
SWAPFILE="${SWAPFILE:-/mnt/cache/.aginfo_swap.img}"

if [[ "${EUID:-}" -ne 0 ]]; then
  echo "Re-run as root (required for mkswap/swapon)." >&2
  exit 1
fi

if [[ -z "${SIZE_GB}" ]] || [[ ! "${SIZE_GB}" =~ ^[0-9]+$ ]] || [[ "${SIZE_GB}" -lt 1 ]]; then
  echo "SWAP_SIZE_GB must be a positive integer (gigabytes)." >&2
  exit 1
fi

mkdir -p "$(dirname "$SWAPFILE")"

if swapon --show | grep -qF "${SWAPFILE}"; then
  echo "Already active: ${SWAPFILE}"
  swapon --show
  exit 0
fi

if [[ ! -f "${SWAPFILE}" ]]; then
  echo "Creating ${SIZE_GB}G swap file at ${SWAPFILE} ..."
  fallocate -l "${SIZE_GB}G" "${SWAPFILE}" || dd if=/dev/zero of="${SWAPFILE}" bs=1M count=$((SIZE_GB * 1024)) status=progress
  chmod 600 "${SWAPFILE}"
  mkswap "${SWAPFILE}"
else
  echo "Using existing ${SWAPFILE} (mkswap skipped)."
fi

swapon "${SWAPFILE}"
echo ""
echo "Swap is now on. swapon --show:"
swapon --show
echo ""
cat <<EOF
--- Persist across reboot (Unraid) ---
Add this line to /boot/config/go (adjust path if needed):

  swapon ${SWAPFILE}

Optional vm tuning (only if you still OOM; slows reclaim):

  sysctl -w vm.swappiness=20
  sysctl -w vm.vfs_cache_pressure=80

Remove swap later: swapoff ${SWAPFILE} && rm -f ${SWAPFILE}
EOF
