# Provenance notes

The evidence set deliberately preserves unsuccessful attempts. They are useful for
auditing the actual path to the completed experiment, but they must not be mistaken
for the final validation state.

## FEMU build

- `build-provenance/bootstrap.status.json` records the first bootstrap attempt,
  which exited with status 1.
- `build-provenance/femu-compile.log` begins with an unsuccessful `make clean`, then
  contains the subsequent successful compilation.
- `build-provenance/final-build-validation.txt`, `qemu-version.txt`,
  `femu-device.txt`, and `qemu-system-x86_64.sha256` are the authoritative final
  build checks. The final binary is QEMU 10.1.0 at the pinned FEMU commit and has
  `cap_ipc_lock=ep`, needed for the 4 GiB memory-backed namespace.

## Guest first boot

- `guest-provenance/first-boot-command.txt` is the initial failed command using an
  obsolete seed-image path.
- The successful launch used the ISO in
  `guest-provenance/cloud-init-seed.sha256`. Its parameters were reconstructed with
  launch-wrapper dry-run and saved as `first-boot-success-command.txt`; it is not a
  byte-for-byte terminal transcript.
- `first-boot-console.log`, `first-boot-device-and-versions.txt`, image hashes, and
  the prepared qcow2 backing-chain record are the authoritative boot/device proof.

## DFTL full run

The start of `full-provenance/dftl4m-gc75-run.log` contains a rejected runner
invocation with an unsupported mapping-cache argument. The runner failed before
opening the benchmark device. The corrected run immediately following it produced
the complete 30 fio JSON files and 60 before/after SMART binary logs. The 4 MiB CMT
was configured at the FEMU host launch layer, where that option belongs.

## Raw versus derived files

Files ending in `.fio.json` and `.waf-*.bin` are raw device evidence. Parsed WAF
JSON, per-run `analysis/`, and `report/` are reproducible derivatives. The global
digest manifest is generated only after the result set is finalized and excludes
itself.
