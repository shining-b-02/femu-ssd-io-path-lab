# Executed experiment manifest

## Fixed environment

| Item | Executed value |
|---|---|
| Host | Ubuntu 24.04.4 LTS, Linux 7.0.0-30-generic, x86_64 |
| CPU / memory | Intel Core i7-1165G7, 8 logical CPUs, 15.3 GiB RAM |
| KVM | `/dev/kvm` readable and writable |
| FEMU source | `MoatLab/FEMU@39664d2424eaa4ebdcf8400f8973d3ad445644a6` |
| QEMU/FEMU binary | QEMU 10.1.0, SHA-256 `017afba8d21f3f064347cde42a31fb141339eebc32fb40df492d0c7b7df457ab` |
| Guest | Ubuntu 24.04.4 LTS, Linux 6.8.0-137-generic, x86_64 |
| Guest tools | fio 3.36, nvme-cli 2.8, Python 3.12.3, Git 2.43.0 |
| Namespace | `/dev/nvme0n1`, `FEMU BlackBox-SSD Controller`, 4,294,967,296 bytes |
| Full profile | 80% target, two precondition passes, 10 s ramp, 60 s runtime, 3 repetitions |
| Common FEMU options | 4 GiB device, greedy GC, GC high threshold 95, default NAND timing/geometry |

The host was recorded with the `powersave` governor. This is a validity limitation,
not a hidden normalization; the same host and governor were retained across all
conditions.

## Condition matrix

| Run directory | FEMU launch parameters | Runner metadata |
|---|---|---|
| `20260821T161041Z__page-gc75` | `--mapping page --gc-threshold 75` | `page`, 75 |
| `20260821T164704Z__dftl4m-gc75` | `--mapping dftl --mapping-cache-mb 4 --gc-threshold 75` | `dftl`, 75 |
| `20260821T172316Z__hybrid-gc75` | `--mapping hybrid --gc-threshold 75` | `hybrid`, 75 |
| `20260821T192637Z__page-gc50` | `--mapping page --gc-threshold 50` | `page`, 50 |
| `20260821T200244Z__page-gc90` | `--mapping page --gc-threshold 90` | `page`, 90 |

The runner has no mapping-cache metadata field. The DFTL cache size is therefore
proved by the host launch command in `full-provenance/dftl4m-gc75-console.log` and
the condition name, while all other runner metadata is in each run's
`metadata.json`.

## Independence and ordering

Every condition began from the same prepared guest base through a newly created
overlay. FEMU was stopped between conditions, so its DRAM-backed SSD state did not
cross condition boundaries. Within a condition, workloads ran in the fixed order
stored in `metadata.json`; preceding workloads can therefore affect later device
state. Results support controlled comparisons within this emulator and run order,
not universal hardware claims.
