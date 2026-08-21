# FEMU SSD I/O Path Lab

FEMU의 NVMe black-box SSD를 대상으로 workload, FTL mapping, GC threshold가 IOPS와 tail latency, write amplification에 미치는 영향을 재현 가능한 방법으로 측정하는 독립 프로젝트입니다.

## 연구 질문

> 같은 NAND timing과 SSD geometry에서 workload 특성 및 FTL 정책 변화는 throughput, p99/p99.9 latency, WAF 사이에 어떤 trade-off를 만드는가?

첫 실험은 아래 두 축을 분리해서 비교합니다.

1. `mapping=page|dftl|hybrid` 비교 (`gc_thres_pcent=75` 고정)
2. `gc_thres_pcent=50|75|90` 비교 (`mapping=page` 고정)

workload는 sequential/random, read/write, 70:30 및 30:70 read/write mix, queue depth 1/32를 포함합니다. 각 측정은 3회 반복하고 중앙값을 사용합니다.

## 현재 상태

- [x] FEMU host 요구사항 검사
- [x] 재현 가능한 FEMU commit 고정
- [x] mapping/GC parameter를 받는 FEMU launch wrapper
- [x] raw device 안전 검증이 포함된 `fio` workload runner
- [x] FEMU SMART vendor field 기반 interval WAF 측정
- [x] JSON 결과를 CSV/Markdown/SVG로 변환하는 분석기
- [x] parser와 command builder 단위 테스트
- [x] Ubuntu CI에서 shell/test/dry-run regression 검증
- [x] macOS ARM64에서 host-side parser 10,000회 측정 및 증거 JSON 보존
- [ ] x86_64 Linux/KVM host에서 첫 실측
- [ ] 실측 결과 기반 가설 검정과 병목 분석

현재 고정한 FEMU revision은 `39664d2424eaa4ebdcf8400f8973d3ad445644a6`입니다. 숫자를 얻기 전까지 성능 결론은 내리지 않습니다.

> **SSD 성능 측정 상태: `X86_64 KVM HOST 확보 전까지 보류`**

## 현재 검증 결과

2026-08-21에 Apple Silicon macOS 환경에서 실험 제어 코드와 결과 처리 경로를 직접 실행했습니다.

| 검증 항목 | 결과 |
|---|---:|
| Python 단위·파이프라인 테스트 | 10개 통과 |
| smoke dry-run에서 생성된 `fio` 명령 | 2개 |
| fio JSON parser 반복 측정 | 10,000회 |
| parser 중앙값 | 18.084 us/parse |
| parser p95 | 20.917 us/parse |
| parser 최댓값 | 230.208 us/parse |
| GitHub Actions | 성공 |

parser 시간은 SSD 성능이 아니라 **host-side 결과 처리 비용**입니다. 원본 측정 증거는
[`results/host-parser-macos-arm64-2026-08-21.json`](results/host-parser-macos-arm64-2026-08-21.json),
전체 해석은 [`docs/ANALYSIS_REPORT_KO.md`](docs/ANALYSIS_REPORT_KO.md)에 보존했습니다.

## 왜 별도 Linux host가 필요한가

현재 개발 머신은 Apple Silicon macOS입니다. FEMU의 정확한 성능 실험은 x86_64 Linux와 KVM hardware virtualization을 요구하므로 이 머신에서 얻은 QEMU/TCG 수치를 성능 결과로 사용하지 않습니다. 공식 요구사항에 맞는 physical x86_64 Linux host 또는 KVM이 노출되는 동등한 환경에서 실행합니다.

UTM에서 x86_64 Linux를 띄우는 것은 가능하지만 Apple Silicon에서는 guest와 host architecture가 달라 hardware virtualization이 아니라 CPU emulation으로 동작합니다. ARM Linux VM의 nested virtualization도 FEMU가 요구하는 x86_64 KVM을 제공하지 않으므로 UTM 결과는 기능 smoke test 외에는 채택하지 않습니다.

## 5분 로컬 검증

macOS에서도 destructive I/O 없이 코드와 명령 생성을 검증할 수 있습니다.

```bash
make test
make dry-run
make host-benchmark
./scripts/launch_femu.sh \
  --build-dir /opt/femu/build-femu \
  --image /var/lib/femu/ubuntu.qcow2 \
  --mapping page \
  --gc-threshold 75 \
  --dry-run
```

## 실제 실행 흐름

### 1. x86_64 Linux host 준비

```bash
./scripts/check_host.sh
./scripts/bootstrap_femu.sh --destination /absolute/path/to/FEMU --install-deps
```

VM image 준비를 포함한 상세 절차는 [docs/SETUP_LINUX.md](docs/SETUP_LINUX.md)에 있습니다.

### 2. host에서 한 condition 실행

```bash
./scripts/launch_femu.sh \
  --build-dir /absolute/path/to/FEMU/build-femu \
  --image /absolute/path/to/u20s.qcow2 \
  --mapping page \
  --gc-threshold 75
```

### 3. guest에서 smoke test

`/dev/nvme0n1`이 FEMU namespace인지 `lsblk`로 확인한 뒤 실행합니다. 아래 명령은 해당 namespace의 데이터를 덮어씁니다.

```bash
python3 -m ssdbench.run_matrix \
  --config configs/workloads.json \
  --profile smoke \
  --target /dev/nvme0n1 \
  --condition page-gc75 \
  --mapping page \
  --gc-threshold 75 \
  --output results \
  --confirm-erase-femu-device
```

smoke test가 성공하면 `--profile full`로 바꿉니다. 다른 mapping/GC condition은 FEMU를 종료하고 새로 부팅하여 SSD 내부 상태를 초기화한 뒤 같은 절차로 실행합니다.

### 4. 결과 분석

```bash
python3 -m ssdbench.analyze --input results --output results/report
```

생성물:

- `runs.csv`: 개별 반복 측정값
- `summary.csv`: condition/workload별 중앙값
- `REPORT.md`: 결과 표와 그림
- `iops.svg`, `p99-latency.svg`, `waf.svg`: 포트폴리오용 초안 그래프

## 저장소 구조

```text
configs/workloads.json      fio workload와 smoke/full profile
scripts/check_host.sh       Linux/x86_64/KVM/RAM/CPU 검사
scripts/bootstrap_femu.sh   고정 revision clone/build
scripts/launch_femu.sh      mapping/GC condition별 FEMU 실행
ssdbench/run_matrix.py      안전한 실험 실행 및 provenance 저장
ssdbench/waf.py             FEMU SMART WAF counter 추출
ssdbench/analyze.py         CSV/Markdown/SVG 분석 리포트
docs/EXPERIMENT_PLAN.md     가설, 변수, 절차, 타당성 위협
docs/IO_PATH.md             관찰할 Linux-to-FTL I/O path
```

## 프로젝트 완료 기준

- 모든 condition에서 동일한 host/guest/FEMU revision과 workload seed 사용
- 3회 반복의 median과 변동성을 함께 보고
- IOPS뿐 아니라 p99/p99.9 및 interval WAF를 함께 해석
- 예상과 다른 결과도 보존하고 원인을 source/trace 수준에서 조사
- raw JSON, metadata, 분석 코드까지 공개하여 제3자가 재현 가능

FEMU와 fio의 원 프로젝트 및 라이선스는 각각의 upstream 저장소를 따릅니다.

이 저장소가 작성한 harness와 문서는 MIT License로 배포합니다.
