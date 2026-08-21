# Measurement evidence

This directory contains the raw and derived evidence for the completed FEMU/KVM
experiment. Raw fio JSON and SMART binary logs are committed directly because the
complete directory is only about 5.3 MiB. Do not replace or normalize the raw
artifacts; regenerate derived reports from them instead.

## Experiment runs

| Directory | Profile | Condition | fio repetitions |
|---|---|---|---:|
| `20260821T160854Z__page-gc75` | smoke | page, GC 75 | 2 |
| `20260821T161041Z__page-gc75` | full | page, GC 75 | 30 |
| `20260821T164704Z__dftl4m-gc75` | full | DFTL, 4 MiB CMT, GC 75 | 30 |
| `20260821T172316Z__hybrid-gc75` | full | hybrid, GC 75 | 30 |
| `20260821T192637Z__page-gc50` | full | page, GC 50 | 30 |
| `20260821T200244Z__page-gc90` | full | page, GC 90 | 30 |

Each full run contains ten workloads, three repetitions per workload, a two-pass
precondition result, fio JSON, and 512-byte SMART logs captured before and after
every repetition. Every condition used a fresh qcow2 overlay and a fresh FEMU
process. See `EXPERIMENT_MANIFEST.md` for the controlled launch parameters.

## Provenance and reports

- `host-provenance/`: host identity, KVM checks, CPU, memory, kernel, and governor.
- `build-provenance/`: pinned FEMU source revision, compiler/build logs, registered
  device, QEMU version, and final binary SHA-256.
- `guest-provenance/`: source and prepared image hashes, backing chain, first boot,
  device identity, tool versions, and guest regression output.
- `smoke-provenance/` and `full-provenance/`: VM console, runner logs, and selected
  artifact hashes.
- `report/`: integrated 150-row analysis plus Phase A/B/C report subsets.
- `PROVENANCE_NOTES.md`: preserved failed attempts and which evidence is
  authoritative.
- `SHA256SUMS.txt`: digest manifest for every result artifact except the manifest
  itself.

Rebuild the integrated report from the raw files:

```bash
python3 -m ssdbench.analyze \
  --input results \
  --output results/report \
  --profile full
```

The explicit profile matters because this directory intentionally contains both
`smoke` and `full` data. The integrated outputs contain 150 run rows, 50 median
summary rows, and 50 variability rows.

Verify the frozen evidence set:

```bash
(cd results && sha256sum -c SHA256SUMS.txt)
```

