#!/usr/bin/env bash
set -euo pipefail

failures=0

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf '[PASS] %s\n' "$label"
    else
        printf '[FAIL] %s\n' "$label"
        failures=$((failures + 1))
    fi
}

is_linux() { [[ "$(uname -s)" == "Linux" ]]; }
is_x86_64() { [[ "$(uname -m)" == "x86_64" ]]; }
has_kvm() { [[ -c /dev/kvm && -r /dev/kvm && -w /dev/kvm ]]; }
has_memory() {
    local mem_kib
    mem_kib=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || printf '0')
    [[ "$mem_kib" -ge 12582912 ]]
}
has_cores() { [[ "$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '0')" -ge 8 ]]; }

printf 'FEMU host readiness\n'
printf '  OS:   %s\n' "$(uname -s)"
printf '  Arch: %s\n' "$(uname -m)"

check 'Linux host' is_linux
check 'x86_64 architecture' is_x86_64
check 'read/write access to /dev/kvm' has_kvm
check 'at least 12 GiB RAM' has_memory
check 'at least 8 logical CPUs' has_cores
check 'git installed' command -v git
check 'Python 3 installed' command -v python3

if (( failures > 0 )); then
    printf '\n%d prerequisite(s) missing. See docs/SETUP_LINUX.md.\n' "$failures"
    exit 1
fi

printf '\nHost is ready for a FEMU build.\n'

