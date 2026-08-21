#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' \
        "Usage: $0 --build-dir PATH --image PATH [options]" \
        '' \
        'Options:' \
        '  --mapping page|dftl|hybrid|fast  (default: page)' \
        '  --mapping-cache-mb N             (default: 0)' \
        '  --gc-policy POLICY               (default: greedy)' \
        '  --gc-threshold N                 (default: 75)' \
        '  --gc-high-threshold N            (default: 95)' \
        '  --device-size-mb N               (default: 4096)' \
        '  --ssh-port N                     (default: 8080)' \
        '  --cloud-init-seed PATH           (optional NoCloud seed image)' \
        '  --dry-run'
}

build_dir=''
image=''
mapping='page'
mapping_cache_mb=0
gc_policy='greedy'
gc_threshold=75
gc_high_threshold=95
device_size_mb=4096
ssh_port=8080
cloud_init_seed=''
dry_run=0

while (($#)); do
    case "$1" in
        --build-dir) build_dir="${2:-}"; shift 2 ;;
        --image) image="${2:-}"; shift 2 ;;
        --mapping) mapping="${2:-}"; shift 2 ;;
        --mapping-cache-mb) mapping_cache_mb="${2:-}"; shift 2 ;;
        --gc-policy) gc_policy="${2:-}"; shift 2 ;;
        --gc-threshold) gc_threshold="${2:-}"; shift 2 ;;
        --gc-high-threshold) gc_high_threshold="${2:-}"; shift 2 ;;
        --device-size-mb) device_size_mb="${2:-}"; shift 2 ;;
        --ssh-port) ssh_port="${2:-}"; shift 2 ;;
        --cloud-init-seed) cloud_init_seed="${2:-}"; shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -z "$build_dir" || "$build_dir" != /* || -z "$image" || "$image" != /* ]]; then
    printf -- '--build-dir and --image must be absolute paths.\n' >&2
    exit 2
fi
if [[ -n "$cloud_init_seed" && "$cloud_init_seed" != /* ]]; then
    printf -- '--cloud-init-seed must be an absolute path.\n' >&2
    exit 2
fi
case "$mapping" in page|dftl|hybrid|fast) ;; *) printf 'Invalid mapping: %s\n' "$mapping" >&2; exit 2 ;; esac
case "$gc_policy" in greedy|random|cost-benefit|fifo|d-choice) ;; *) printf 'Invalid GC policy: %s\n' "$gc_policy" >&2; exit 2 ;; esac
for numeric in "$mapping_cache_mb" "$gc_threshold" "$gc_high_threshold" "$device_size_mb" "$ssh_port"; do
    [[ "$numeric" =~ ^[0-9]+$ ]] || { printf 'Expected integer, got: %s\n' "$numeric" >&2; exit 2; }
done
(( gc_threshold >= 1 && gc_threshold < gc_high_threshold && gc_high_threshold <= 100 )) || {
    printf 'Require 1 <= GC threshold < high threshold <= 100.\n' >&2
    exit 2
}

qemu_bin="$build_dir/qemu-system-x86_64"
if (( ! dry_run )); then
    [[ "$(uname -s)" == 'Linux' && "$(uname -m)" == 'x86_64' ]] || {
        printf 'FEMU measurements require an x86_64 Linux host.\n' >&2
        exit 1
    }
    [[ -x "$qemu_bin" ]] || { printf 'FEMU binary not found: %s\n' "$qemu_bin" >&2; exit 1; }
    [[ -f "$image" ]] || { printf 'VM image not found: %s\n' "$image" >&2; exit 1; }
    if [[ -n "$cloud_init_seed" ]]; then
        [[ -f "$cloud_init_seed" ]] || {
            printf 'Cloud-init seed image not found: %s\n' "$cloud_init_seed" >&2
            exit 1
        }
    fi
    [[ -r /dev/kvm && -w /dev/kvm ]] || { printf 'No read/write access to /dev/kvm.\n' >&2; exit 1; }
fi

femu_options="femu,devsz_mb=${device_size_mb},namespaces=1,femu_mode=1"
femu_options+=",secsz=512,secs_per_pg=8,pgs_per_blk=256,blks_per_pl=256,pls_per_lun=1"
femu_options+=",luns_per_ch=8,nchs=8,pg_rd_lat=40000,pg_wr_lat=200000,blk_er_lat=2000000,ch_xfer_lat=0"
femu_options+=",gc_thres_pcent=${gc_threshold},gc_thres_pcent_high=${gc_high_threshold}"
femu_options+=",mapping=${mapping},mapping_cache_mb=${mapping_cache_mb},gc_policy=${gc_policy}"

command=(
    "$qemu_bin"
    -name "FEMU-${mapping}-gc${gc_threshold}"
    -enable-kvm
    -cpu host
    -smp 4
    -m 4G
    -device virtio-scsi-pci,id=scsi0
    -device scsi-hd,drive=hd0
    -drive "file=${image},if=none,aio=native,cache=none,format=qcow2,id=hd0"
)
if [[ -n "$cloud_init_seed" ]]; then
    command+=(
        -drive "file=${cloud_init_seed},if=virtio,format=raw,readonly=on"
    )
fi
command+=(
    -device "$femu_options"
    -net "user,hostfwd=tcp::${ssh_port}-:22"
    -net nic,model=virtio
    -nographic
    -qmp "unix:${build_dir}/qmp-sock,server,nowait"
)

printf 'Condition: mapping=%s mapping_cache_mb=%s gc_policy=%s gc=%s/%s\n' \
    "$mapping" "$mapping_cache_mb" "$gc_policy" "$gc_threshold" "$gc_high_threshold"
printf 'Command:'
printf ' %q' "${command[@]}"
printf '\n'

if (( dry_run )); then
    exit 0
fi

exec "${command[@]}"
