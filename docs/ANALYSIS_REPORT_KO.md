# FEMU SSD I/O Path Lab 분석 리포트

## 1. 분석 목적

이 프로젝트는 FEMU NVMe black-box SSD의 I/O 경로에서 workload, FTL mapping, GC threshold가 IOPS, tail latency, write amplification에 미치는 영향을 동일 조건으로 비교하기 위한 실험 harness다. 이번 검증의 목적은 SSD 성능 수치를 만들기 전에 실험 제어, 안전장치, 데이터 파싱, 집계, 리포트 생성 경로가 재현 가능하게 동작하는지 확인하는 것이다.

## 2. 검증 환경

| 항목 | 값 |
|---|---|
| 실행일 | 2026-08-21 |
| 운영체제 | macOS 26.5.2 (25F84) |
| CPU 아키텍처 | arm64 |
| Python | 3.14.0 |
| 프로젝트 branch | `docs/measured-validation-report` |
| FEMU 고정 revision | `39664d2424eaa4ebdcf8400f8973d3ad445644a6` |

Apple Silicon은 x86_64 KVM을 제공하지 않으므로 이번 결과에는 FEMU SSD의 IOPS·latency·WAF 수치를 포함하지 않는다. 아래 값은 현재 머신에서 실제 실행한 host-side 검증 결과다.

## 3. 실행 결과

### 3.1 단위·파이프라인 테스트

`make test`로 다음 경로를 검증했다.

- fio JSON에서 read/write IOPS, bandwidth, p99, p99.9 추출
- 세 번 반복값의 median 집계
- raw artifact에서 CSV·Markdown·SVG 생성
- workload 설정 검증과 결정적 `fio` 명령 생성
- FEMU SMART vendor counter에서 interval WAF 계산
- 손상되거나 짧은 SMART log 거부
- parser microbenchmark 결과 schema 검증

결과는 **10개 테스트 전체 통과**, unittest 내부 실행 시간 0.010초였다.

### 3.2 destructive I/O 방지 경로

`make dry-run`은 실제 block device를 열지 않고 다음 두 smoke workload 명령을 생성했다.

- `randread-4k-qd1`: 4 KiB random read, queue depth 1, runtime 5초
- `randwrite-4k-qd1`: 4 KiB random write, queue depth 1, runtime 5초

두 명령 모두 `direct=1`, `randrepeat=1`, `allrandrepeat=1`, 고정 percentile 목록을 포함했다. live 실행은 Linux block device 확인, mount 여부 확인, `FEMU` model 문자열 확인, 명시적 erase 승인 없이는 시작되지 않는다.

### 3.3 host-side parser 측정

`scripts/benchmark_parser.py`로 100회 warm-up 후 동일한 fio JSON fixture를 10,000회 파싱했다.

| 지표 | 측정값 |
|---|---:|
| 반복 횟수 | 10,000 |
| 중앙값 | 18,084 ns/parse |
| p95 | 20,917 ns/parse |
| 최댓값 | 230,208 ns/parse |

이 값은 분석 코드의 host-side 처리 비용이며 SSD media latency와 관계없는 지표다. 원본 JSON은 `results/host-parser-macos-arm64-2026-08-21.json`에 있다.

### 3.4 원격 회귀 검증

GitHub Actions의 Ubuntu 24.04 CI run `32465796013`에서 shell syntax, Python 테스트, dry-run matrix가 성공했다. 따라서 macOS와 Linux에서 핵심 제어 경로가 모두 검증됐다.

## 4. 코드 관점 분석

실험 runner는 raw device를 다루는 위험을 줄이기 위해 실행 전 네 단계 검사를 수행한다. Linux 여부, block-device type, mount 상태, FEMU model 식별을 모두 통과해야 하며 `--confirm-erase-femu-device`가 없으면 중단한다. 결과 디렉터리에는 host, kernel, Python, fio, nvme-cli, 프로젝트 commit, 예상 FEMU revision을 함께 기록하므로 결과 파일만으로도 provenance를 추적할 수 있다.

분석기는 read/write가 함께 존재하는 workload에서 활성 방향 중 더 나쁜 tail latency를 대표값으로 선택한다. WAF는 누적 counter 자체가 아니라 workload 전후 delta로 계산하기 때문에 이전 실험의 누적 상태가 직접 섞이지 않는다.

## 5. 남은 실측과 완료 조건

x86_64 Linux/KVM host가 확보되면 다음 순서로 성능 실험을 수행한다.

1. 고정 revision FEMU를 동일 host에서 build한다.
2. mapping 비교는 GC threshold 75로 고정한다.
3. GC threshold 비교는 page mapping으로 고정한다.
4. 각 condition을 새 FEMU boot로 초기화하고 full profile을 3회 수행한다.
5. median과 반복 간 변동, p99/p99.9, interval WAF를 함께 분석한다.

현재 저장소는 실험 코드와 검증 경로까지 완성됐으며, SSD 성능 결론은 위 hardware 조건에서 생성된 raw JSON과 SMART counter가 확보된 뒤에만 추가한다.
