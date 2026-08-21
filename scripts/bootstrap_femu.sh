#!/usr/bin/env bash
set -euo pipefail

readonly FEMU_REPOSITORY='https://github.com/MoatLab/FEMU.git'
readonly FEMU_PINNED_REF='39664d2424eaa4ebdcf8400f8973d3ad445644a6'

usage() {
    printf 'Usage: %s --destination PATH [--install-deps]\n' "$0"
}

destination=''
install_deps=0
while (($#)); do
    case "$1" in
        --destination)
            destination="${2:-}"
            shift 2
            ;;
        --install-deps)
            install_deps=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$destination" || "$destination" != /* ]]; then
    printf -- '--destination must be an absolute path.\n' >&2
    exit 2
fi

"$(dirname "$0")/check_host.sh"

if [[ -e "$destination" ]]; then
    printf 'Destination already exists; refusing to overwrite: %s\n' "$destination" >&2
    exit 2
fi

git clone "$FEMU_REPOSITORY" "$destination"
git -C "$destination" checkout --detach "$FEMU_PINNED_REF"
mkdir -p "$destination/build-femu"
cp "$destination/femu-scripts/femu-copy-scripts.sh" "$destination/build-femu/"
(
    cd "$destination/build-femu"
    ./femu-copy-scripts.sh .
    if (( install_deps )); then
        sudo ./pkgdep.sh
    else
        printf 'Dependencies were not modified. Run sudo ./pkgdep.sh if needed.\n'
    fi
    ./femu-compile.sh
    ./qemu-system-x86_64 -device help | grep femu
)

printf 'Built FEMU at %s/build-femu/qemu-system-x86_64\n' "$destination"

