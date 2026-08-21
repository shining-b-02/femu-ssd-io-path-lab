# x86_64 Linux/KVM 실행 환경

## 요구사항

FEMU 공식 요구사항을 기준으로 다음 환경을 사용한다.

- x86_64 Linux host
- Intel VT-x 또는 AMD-V와 `/dev/kvm` 접근
- 최소 8 logical CPU, 12 GiB RAM, 20 GiB 여유 공간
- 가능하면 nested VM이 아닌 physical host

Apple Silicon macOS의 QEMU TCG 결과는 이 프로젝트의 성능 데이터로 사용하지 않는다.

## 1. host 검사

프로젝트를 Linux host에 복사한 뒤 실행한다.

```bash
./scripts/check_host.sh
```

`/dev/kvm` 권한만 실패하면 현재 사용자를 배포판의 `kvm` group에 추가한 뒤 다시 로그인한다. 시스템 권한 변경은 해당 host 관리자 정책에 맞춰 수행한다.

## 2. FEMU build

아래 스크립트는 공식 MoatLab/FEMU 저장소를 clone하고 프로젝트가 고정한 revision을 checkout한다. 목적지가 이미 존재하면 덮어쓰지 않고 중단한다.

```bash
./scripts/bootstrap_femu.sh \
  --destination /absolute/path/to/FEMU \
  --install-deps
```

성공 기준:

```text
name "femu", bus PCI, desc "FEMU Non-Volatile Memory Express"
```

## 3. guest image

FEMU upstream의 prebuilt Ubuntu image를 사용하거나 Ubuntu Server amd64 qcow2 image를 직접 만든다. guest에는 다음 도구가 필요하다.

```bash
sudo apt-get update
sudo apt-get install -y fio nvme-cli python3 git
```

guest 안에서 이 프로젝트를 clone/copy한다. 결과를 host로 가져올 수 있도록 SSH도 활성화한다.

## 4. 첫 boot

host에서 실행한다.

```bash
./scripts/launch_femu.sh \
  --build-dir /absolute/path/to/FEMU/build-femu \
  --image /absolute/path/to/u20s.qcow2 \
  --mapping page \
  --gc-threshold 75
```

guest에서 검사한다.

```bash
lsblk -o NAME,SIZE,TYPE,MODEL,MOUNTPOINT
sudo nvme id-ctrl /dev/nvme0
sudo nvme smart-log /dev/nvme0n1
```

OS가 있는 virtio/scsi disk와 FEMU NVMe namespace를 혼동하지 않는다. benchmark namespace 및 child partition에 mountpoint가 없어야 한다.

## 5. smoke 후 full

```bash
sudo -E python3 -m ssdbench.run_matrix \
  --config configs/workloads.json \
  --profile smoke \
  --target /dev/nvme0n1 \
  --condition page-gc75 \
  --mapping page \
  --gc-threshold 75 \
  --output results \
  --confirm-erase-femu-device
```

smoke 결과가 정상일 때만 `--profile full`을 실행한다.

## 6. condition matrix

한 condition의 full run이 끝날 때마다 guest를 정상 종료하고 다음 FEMU process를 새로 시작한다.

| Condition | launch option |
|---|---|
| page-gc75 | `--mapping page --gc-threshold 75` |
| dftl4m-gc75 | `--mapping dftl --mapping-cache-mb 4 --gc-threshold 75` |
| hybrid-gc75 | `--mapping hybrid --gc-threshold 75` |
| page-gc50 | `--mapping page --gc-threshold 50` |
| page-gc90 | `--mapping page --gc-threshold 90` |

guest runner의 `--condition`, `--mapping`, `--gc-threshold` metadata가 host launch option과 정확히 일치해야 한다.

## 7. 결과 회수와 분석

모든 `results/<timestamp>__<condition>` 디렉터리를 한곳에 모은 뒤 실행한다.

```bash
python3 -m ssdbench.analyze --input results --output results/report
```

raw JSON과 SMART binary log를 지우지 않는다. 분석 코드가 바뀌어도 원본에서 다시 계산할 수 있어야 한다.

