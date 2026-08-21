# FEMU SSD I/O Path Lab 최종 분석

## 1. 결론 요약

2026-08-22 KST에 x86_64 Linux/KVM host에서 고정 FEMU revision
`39664d2424eaa4ebdcf8400f8973d3ad445644a6`을 실제로 빌드하고, smoke와 5개
full condition을 완료했다. Full data는 10 workload × 3 repetitions × 5
conditions, 총 150개 fio JSON과 각 반복 전후의 SMART binary log로 구성된다.

관찰된 핵심은 다음과 같다.

1. Page mapping에서 QD32는 QD1보다 IOPS를 크게 높였지만 p99/p99.9도 함께
   악화됐다. 높은 QD의 throughput/tail trade-off가 분명했다.
2. DFTL 4 MiB는 page보다 전체 normalized geometric mean IOPS가 14.8% 낮고
   p99가 62.3% 높았다. WAF 차이보다 translation cache miss/dirty eviction timing이
   주요 설명이다.
3. Hybrid는 random/mixed write에서 interval WAF 244–259와 수백 ms에서 수 초의
   tail을 보였다. 16개 log block과 random overwrite에서 반복되는 full merge라는
   pinned source 구현이 이 급격한 붕괴를 설명한다.
4. Page mapping의 GC threshold 50은 write-heavy 구간 WAF 1.125, 75는 1.027,
   90은 1.012였다. Threshold 50이 이 구현에서 더 일찍 GC를 시작하기 때문이다.
5. 대부분 IOPS/p99 반복은 안정적이었지만 hybrid mixed p99.9는 크게 흔들렸다.
   극단 tail은 관찰 사실로 남기되 3회 반복으로 일반화하지 않는다.

이 결론은 실제 SSD 전체가 아니라 이 FEMU revision, geometry, timing, run order에
대한 것이다.

## 2. 환경과 provenance

| 항목 | 실행값 |
|---|---|
| Host | Ubuntu 24.04.4 LTS, Linux 7.0.0-30-generic, x86_64 |
| CPU / RAM | Intel Core i7-1165G7, 8 logical CPUs, 15.3 GiB |
| Host governor | `powersave` |
| KVM | `/dev/kvm` read/write 통과 |
| FEMU/QEMU | pinned source, QEMU 10.1.0 |
| FEMU binary SHA-256 | `017afba8d21f3f064347cde42a31fb141339eebc32fb40df492d0c7b7df457ab` |
| Guest | Ubuntu 24.04.4, Linux 6.8.0-137-generic |
| Guest tools | fio 3.36, nvme-cli 2.8, Python 3.12.3, Git 2.43.0 |
| Target | `/dev/nvme0n1`, FEMU BlackBox-SSD Controller, 4 GiB, unmounted |
| Harness revision | `00d67436b3484514462413e4ea76db7edfbd23d0` |

각 condition은 동일한 prepared guest base의 fresh qcow2 overlay와 새 FEMU
process로 시작했다. OS disk는 `/dev/sda`, benchmark namespace는
`/dev/nvme0n1`으로 분리됐으며 destructive runner는 block type, mount 여부,
model 문자열, 명시적 승인까지 확인했다.

Build와 first-boot 과정의 첫 실패 로그도 삭제하지 않았다. 최종 성공 증거와 구별
방법은 `results/PROVENANCE_NOTES.md`, 실제 condition은
`results/EXPERIMENT_MANIFEST.md`에 기록했다.

## 3. 측정과 집계

Full profile은 namespace의 80%를 대상으로 4 KiB random write precondition을
2회 수행한 뒤, 각 workload를 ramp 10초와 runtime 60초로 3회 실행했다. fio는
`libaio`, `direct=1`, 고정 random repeat를 사용했다.

FEMU SMART vendor 영역은 다음 누적 counter를 제공한다.

- byte 192: cumulative `waf_x1000` (`uint32`, little endian)
- byte 200: cumulative host write pages (`uint64`, little endian)
- byte 208: cumulative GC relocated pages (`uint64`, little endian)

보고한 WAF는 누적 WAF snapshot이 아니라 workload 전후 delta다.

```text
interval_WAF = (delta_host_write_pages + delta_gc_write_pages)
               / delta_host_write_pages
```

Read-only 구간처럼 host write delta가 0이면 WAF는 1.0으로 표시하되 raw delta를
함께 보존했다. 표는 repetition 중앙값이며 mixed workload tail은 read/write 중 더
나쁜 활성 방향이다. `variability.csv`는 각 metric의 min/median/max/relative range를
추가로 제공한다.

## 4. Phase A — page mapping workload 특성

GC threshold 75를 고정한 page mapping 결과다.

| Workload | IOPS | BW (MiB/s) | p99 (us) | p99.9 (us) | WAF |
|---|---:|---:|---:|---:|---:|
| randread-4k-qd1 | 26,722.4 | 104.4 | 49.4 | 58.6 | 1.000 |
| randread-4k-qd32 | 308,053.4 | 1,203.3 | 166.9 | 212.0 | 1.000 |
| randwrite-4k-qd1 | 4,774.5 | 18.7 | 226.3 | 354.3 | 1.000 |
| randwrite-4k-qd32 | 145,746.3 | 569.3 | 252.9 | 3,784.7 | 1.027 |
| read-128k-qd1 | 10,154.9 | 1,269.4 | 164.9 | 205.8 | 1.000 |
| read-128k-qd32 | 65,952.2 | 8,244.1 | 839.7 | 1,011.7 | 1.000 |
| write-128k-qd1 | 4,596.7 | 574.6 | 224.3 | 2,146.3 | 1.000 |
| write-128k-qd32 | 9,622.7 | 1,202.9 | 5,210.1 | 5,275.6 | 1.000 |
| randrw70-4k-qd32 | 248,804.9 | 971.9 | 272.4 | 391.2 | 1.027 |
| randrw30-4k-qd32 | 176,035.2 | 687.6 | 250.9 | 3,686.4 | 1.027 |

QD1→32의 변화는 다음과 같다.

| Pair | IOPS 배수 | p99 배수 | p99.9 배수 |
|---|---:|---:|---:|
| randread 4 KiB | 11.53× | 3.38× | 3.62× |
| randwrite 4 KiB | 30.53× | 1.12× | 10.68× |
| read 128 KiB | 6.49× | 5.09× | 4.92× |
| write 128 KiB | 2.09× | 23.23× | 2.46× |

QD가 NAND parallelism과 outstanding command를 활용해 throughput을 높였지만,
완료 대기열이 길어지면서 tail 비용도 커졌다. Randwrite QD32는 p99 상승이 작아
보여도 p99.9가 3.785 ms로 10.68배 증가했으므로 p99 하나만으로는 trade-off를
놓친다.

Mixed workload에서 read 70%→30%로 write 비중을 높이면 IOPS는 29.2% 줄고
p99.9는 0.391 ms에서 3.686 ms로 9.42배 증가했다. Interval WAF 중앙값은 둘 다
1.027이므로 이 tail 차이는 단순히 relocation page 비율 하나로만 설명되지 않는다.

H1은 현재 matrix에서 검정 불충분이다. Sequential은 128 KiB, random은 4 KiB라
block size가 동시에 바뀐다. 동일 block size의 sequential/random pair를 추가하기
전에는 access pattern의 독립 효과라고 부르지 않는다.

## 5. Phase B — mapping 비교

GC threshold 75를 고정했다.

| Mapping | Workload | IOPS | p99 (us) | p99.9 (us) | WAF |
|---|---|---:|---:|---:|---:|
| page | randwrite 4K QD1 | 4,774.5 | 226.3 | 354.3 | 1.000 |
| DFTL | randwrite 4K QD1 | 4,322.7 | 411.6 | 477.2 | 1.000 |
| hybrid | randwrite 4K QD1 | 4.1 | 278,921.2 | 283,115.5 | 244.157 |
| page | randwrite 4K QD32 | 145,746.3 | 252.9 | 3,784.7 | 1.027 |
| DFTL | randwrite 4K QD32 | 98,381.9 | 880.6 | 3,850.2 | 1.027 |
| hybrid | randwrite 4K QD32 | 113.5 | 734,003.2 | 11,878,268.9 | 255.642 |
| page | randrw70 4K QD32 | 248,804.9 | 272.4 | 391.2 | 1.027 |
| DFTL | randrw70 4K QD32 | 154,825.3 | 700.4 | 1,056.8 | 1.028 |
| hybrid | randrw70 4K QD32 | 390.8 | 708,837.4 | 1,132,462.1 | 258.773 |
| page | randrw30 4K QD32 | 176,035.2 | 250.9 | 3,686.4 | 1.027 |
| DFTL | randrw30 4K QD32 | 111,558.2 | 831.5 | 3,719.2 | 1.027 |
| hybrid | randrw30 4K QD32 | 161.9 | 742,391.8 | 2,264,924.2 | 257.688 |

열 workload별 page-normalized ratio의 geometric mean에서 DFTL은 IOPS 0.852,
p99 1.623이었다. DFTL과 page의 write-heavy WAF가 거의 같으므로 relocation
증가가 아니라 mapping timing이 더 직접적인 후보다. Pinned source의
`hw/femu/bbssd/ftl-map-cmt.c`는 CMT hit에는 추가 latency를 넣지 않지만 miss에는
translation-page NAND read를 넣고, dirty eviction에는 NAND write 후 직렬화된
read까지 넣는다. 4 MiB/4 KiB 설정은 translation page 1,024개를 cache하며 한
translation page는 512 LPN entry를 담는다.

Hybrid의 random-write IOPS는 page보다 QD1 약 1,170배, QD32 약 1,284배 낮았다.
`hw/femu/bbssd/ftl-map-hybrid.c`의 기본 log block pool은 16개다. Random overwrite는
256-page 순차 switch-merge 조건을 충족하지 못하고, pool이 차면 가장 찬 log
block을 골라 valid page마다 NAND read/write와 `gc_write_pages`를 과금하는 full
merge를 한다. `ftl-datapath.c`는 host request마다 reclaim을 수행할 수 있어 이
비용이 foreground latency에 직접 보인다. 즉 WAF 250 전후와 수백 ms tail은 같은
구현 경로의 두 신호다.

Hybrid 파일 상단 설명은 allocator hook이 미래 작업인 것처럼 적혀 있지만 현재
코드는 LOG class allocation과 실제 relocation을 수행한다. 측정 해석에는 실행되는
코드를 따랐으며, 이 주석 불일치는 upstream 유지보수 위험으로 기록한다.

## 6. Phase C — page mapping GC threshold

| Threshold | randwrite QD32 IOPS | p99 (us) | p99.9 (us) | WAF | randrw30 p99.9 (us) |
|---:|---:|---:|---:|---:|---:|
| 50 | 135,338.5 | 280.6 | 8,978.4 | 1.125 | 8,847.4 |
| 75 | 145,746.3 | 252.9 | 3,784.7 | 1.027 | 3,686.4 |
| 90 | 143,889.4 | 272.4 | 2,900.0 | 1.012 | 2,801.7 |

`hw/femu/bbssd/ftl-geom.c`는 사용자 threshold를
`(1 - pcent/100) * total_lines` free-line 수로 바꾸고, `ftl-internal.h`와
`ftl.c`는 free line이 그 값 이하가 되면 GC를 시작한다. 따라서 숫자 50은 90보다
더 많은 free line이 남았을 때, 즉 더 일찍 GC를 동작시킨다. 이 60초 측정창에서
50의 write-heavy interval WAF가 가장 높았던 것은 그 의미와 일치한다.

열 workload 전체의 page-gc75 대비 normalized geometric mean은 page-gc50이
IOPS 0.951/p99 1.090, page-gc90이 IOPS 0.949/p99 1.106이었다. 이 run에서는 75가
전체적으로 가장 좋았지만 차이가 작은 workload도 많고 read-only 결과도 condition
간 달라졌다. 고정 순서와 host noise가 섞이므로 threshold 75를 일반 최적값으로
확정하지 않는다. H4의 “early GC가 tail을 완화한다”는 이번 window에서는 지지되지
않았고, 오히려 threshold 50의 WAF와 p99.9가 커졌다.

## 7. 반복 변동성

`results/report/variability.csv`의 전체 50 group을 검사했다.

- IOPS 상대 범위 최대: hybrid randwrite QD1, 7.61%.
- p99 상대 범위 최대: page-gc90 write 128 KiB QD1, 11.26%.
- WAF 상대 범위 최대: hybrid randrw70, 2.09%.
- p99.9 상대 범위 최대: hybrid randrw30, 393.70%.

Hybrid randrw30의 세 p99.9는 1.619 s, 2.265 s, 10.536 s 범위였다. Hybrid
randrw70도 p99.9 상대 범위가 104.81%였다. 반면 중앙값 WAF는 안정적이므로 merge
양은 일관되지만 개별 merge가 completion tail에 나타나는 시점은 크게 흔들렸다고
해석할 수 있다. 이는 source 동작과 지표를 함께 본 추론이며 별도 trace로 직접
입증한 것은 아니다.

## 8. 가설 판정

| 가설 | 판정 | 근거와 제한 |
|---|---|---|
| H1 random write가 sequential보다 WAF/tail 증가 | 검정 불충분 | 4 KiB random과 128 KiB sequential이라 pattern과 block size가 confounded |
| H2 높은 QD가 IOPS와 tail을 함께 증가 | 지지 | 네 read/write pair 모두 IOPS 증가, 모든 pair에서 p99 또는 p99.9 증가 |
| H3 DFTL/hybrid mapping penalty | 지지 | DFTL CMT timing과 hybrid merge 경로가 측정 결과와 일치; hybrid는 극단적 |
| H4 early GC가 sharp tail 완화 가능 | 이번 실행에서 비지지 | threshold 50이 write-heavy WAF와 p99.9를 키움; runtime/order 제한 존재 |

## 9. 타당성 위협과 다음 실험

- FEMU timing/FTL은 실제 controller firmware와 NAND를 그대로 재현하지 않는다.
- Condition은 독립 부팅했지만 한 condition 안의 10 workload는 고정 순서다.
- 60초 runtime과 3회 반복은 p99.9, 특히 초 단위 hybrid tail에 부족할 수 있다.
- Host governor가 `powersave`였고 CPU pinning, poller affinity, `perf` trace가 없다.
- Phase A의 access pattern과 block size가 함께 변한다.
- DFTL cache size는 host launch 증거에 있으나 현재 runner metadata schema에는
  전용 field가 없다.

다음 실험은 동일 4 KiB sequential/random pair, workload별 fresh FEMU boot,
10회 이상 반복, 더 긴 steady-state window, CPU/poller pinning, merge/GC trace를
우선한다. Hybrid는 log-block 수 sweep을 추가하면 원인 가설을 직접 검증할 수 있다.

## 10. 재계산과 원본

```bash
python3 -m ssdbench.analyze \
  --input results \
  --output results/report \
  --profile full
(cd results && sha256sum -c SHA256SUMS.txt)
```

- `results/report/runs.csv`: 150개 repetition metric
- `results/report/summary.csv`: 50개 median group
- `results/report/variability.csv`: 50개 min/median/max/range group
- `results/report/phase-a|phase-b|phase-c/`: 단계별 표와 SVG
- `results/<timestamp>__<condition>/`: fio JSON, SMART binary/parse, metadata
- `results/host-provenance|build-provenance|guest-provenance/`: 환경과 binary/image 증거
- `results/full-provenance/`: condition별 console/runner log와 key-file hash

이전에 macOS arm64에서 얻은 parser microbenchmark는 host-side JSON 처리 비용이며
SSD media latency나 이번 FEMU 성능 결과에 포함하지 않았다.
