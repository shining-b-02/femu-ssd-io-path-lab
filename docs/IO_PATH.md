# I/O path와 source-level 측정 해석

아래 source 위치는 측정에 사용한 FEMU revision
`39664d2424eaa4ebdcf8400f8973d3ad445644a6` 기준이다.

```text
fio (libaio, direct=1)
  -> Linux syscall / block layer / blk-mq
  -> Linux nvme driver
  -> virtual PCIe/NVMe submission queue
  -> FEMU NVMe request/poller
  -> BBSSD ssd_read() / ssd_write()
       -> mapping translate / prepare / commit
       -> optional DFTL CMT timing
       -> NAND channel/LUN timing
       -> mapping-specific hybrid reclaim
       -> base line GC
  -> NVMe completion queue
  -> fio completion latency histogram
```

## 측정 지점

| 계층 | 관찰값 | 원본 |
|---|---|---|
| fio | read/write IOPS, bandwidth, p99, p99.9, error, runtime | `*.fio.json` |
| FTL | host programmed pages, relocated pages, cumulative WAF | SMART vendor bytes 192/200/208 |
| Harness | workload 전후 delta와 interval WAF | `*.waf-before/after.{bin,json}` |
| Environment | host/guest/kernel/tool/device/condition/revision | `metadata.json`, provenance directories |

Mixed workload의 단일 tail 값은 활성 read/write 방향 중 더 나쁜 값을 선택한다.
원본 fio JSON과 `runs.csv`에는 방향별 값이 남아 있다.

## Page mapping과 공통 write path

`hw/femu/bbssd/ftl-datapath.c:72-157`의 `ssd_write()`는 다음 순서로 동작한다.

1. high-threshold foreground GC를 필요한 만큼 실행한다(91-96).
2. Mapping scheme의 `prepare_write()`로 placement class를 고른다(113-120).
3. mapping을 commit하고 valid page로 표시한다(121-123).
4. host가 program한 page마다 `host_write_pages`를 증가시킨다(124).
5. NAND write latency를 channel/LUN timeline에 반영한다(136-142).
6. Scheme이 요구하면 host request 뒤에 reclaim 한 번을 수행한다(145-155).

Page mapping은 full DRAM L2P를 사용하고 scheme-specific reclaim이 없다. Base line
GC는 `hw/femu/bbssd/ftl.c:275-291`에서 background pass로 호출되고,
`ftl-line-gc.c`의 victim relocation이 `gc_write_pages`를 증가시킨다.

## DFTL CMT 경로

`hw/femu/bbssd/ftl.c:101-117`에서 `mapping=dftl`은 CMT를 활성화한다. Cache size를
명시하지 않아도 4 MiB이며 page mapping에는 이 비용을 넣지 않는다. 이번 실험은
4 MiB를 명시했다.

Read와 write는 각각 `ftl-datapath.c:36-40`, `99-103`에서 LPN마다
`cmt_touch()`를 호출한다. `ftl-map-cmt.c:69-129`의 비용 모델은 다음과 같다.

- hit: reference/dirty bit만 갱신, 추가 latency 없음;
- miss: translation page의 home LUN에서 NAND read;
- dirty victim: victim home LUN에 NAND write 후 새 translation read를 직렬 실행.

이번 geometry에서 4 MiB/4 KiB = 1,024 translation pages가 cache되고 한
translation page는 4 KiB / 8-byte PPA = 512 LPN을 담는다. DFTL과 page의
write-heavy interval WAF는 비슷하지만 DFTL p99가 더 큰 결과는 relocation보다 이
translation timing을 병목 후보로 지지한다.

## Hybrid BAST merge 경로

`hw/femu/bbssd/ftl-map-hybrid.c:26-70`은 16개 log block pool을 초기화한다.
Write가 log block의 다음 offset과 맞을 때만 sequential count가 올라가며(152-160),
log block이 가득 차거나 16개 slot이 모두 사용되면 reclaim이 필요하다(163-179).

Reclaim은 가장 찬 log를 하나 고른다(194-213).

- 256 page가 순서대로 채워졌으면 switch merge로 old block erase만 과금한다
  (215-223).
- 그 외에는 full merge로 모든 valid LPN을 NAND read하고 새 DATA page에 write한
  뒤 mapping/rmap을 바꾸며, page마다 `gc_write_pages`를 증가시킨다(224-251).

Random overwrite는 sequential 조건을 쉽게 깨고 많은 data block을 건드려 작은
pool을 소진한다. `ssd_write()`가 request마다 reclaim 한 번을 foreground에서 받을
수 있으므로 WAF 244–259, 수백 ms p99, 초 단위 p99.9가 함께 나타난다. 이는
측정값과 source를 연결한 설명이며 merge trace를 직접 수집한 인과 실험은 아니다.

파일 상단 12-20행은 physical log allocation이 미래 hook인 것처럼 설명하지만 현재
datapath와 reclaim은 class-aware allocation과 실제 relocation을 수행한다. 이 낡은
주석은 실행 코드와 분리해 취급했다.

## GC threshold의 실제 의미

`hw/femu/bbssd/ftl-geom.c:140-143`은 percentage를 다음 free-line threshold로
변환한다.

```text
gc_thres_lines = (1 - gc_thres_pcent / 100) * total_lines
```

`ftl-internal.h:154-163`은 `free_line_cnt <= threshold`일 때 GC를 요청한다.
따라서 이 FEMU option에서 50은 90보다 이른 GC다. 사용자 숫자의 크기만 보고
“90이 더 aggressive하다”고 해석하면 반대가 된다.

Base GC의 greedy victim selection과 relocation은 `ftl-line-gc.c`에 있고, 공통
default device property와 timing은 `hw/femu/femu.c:1405-1423`에 등록된다.
이번 실험은 page read 40 us, page program 200 us, block erase 2 ms와 high
threshold 95 등 공통값을 condition 사이에 바꾸지 않았다.

## SMART WAF 경로

`hw/femu/bbssd/ftl.c:155-180`은 cumulative
`(host_write_pages + gc_write_pages) / host_write_pages`를 x1000 값과 raw counter로
노출한다. `hw/femu/nvme-admin.c:1002-1016`은 NVMe SMART 512-byte log에 이를
little-endian으로 쓴다.

| Byte offset | Type | 값 |
|---:|---|---|
| 192 | uint32 | cumulative WAF × 1000 |
| 200 | uint64 | host write pages |
| 208 | uint64 | GC/merge relocated pages |

Harness는 전후 raw SMART log를 먼저 저장하고 이 counter delta로 interval WAF를
계산한다. 따라서 이전 workload의 누적 counter가 현재 workload 분자에 그대로
섞이지 않는다. 단, 이전 workload가 남긴 physical state의 영향까지 제거하는 것은
아니므로 workload별 fresh boot가 후속 검증이다.

## 병목 후보와 다음 판별법

| 후보 | 이번 신호 | 직접 검증할 후속 실험 |
|---|---|---|
| Queueing/NAND parallelism | QD32 IOPS와 tail 동시 증가 | QD 1/2/4/8/16/32 sweep |
| DFTL translation cache | 비슷한 WAF에서 DFTL p99 증가 | cache size/locality sweep, CMT hit/miss export |
| Hybrid full merge | WAF 약 250과 수백 ms tail 동시 발생 | log count sweep, switch/full merge trace |
| Base GC relocation | page threshold별 WAF 1.125→1.012 | workload별 fresh boot, 더 긴 steady state |
| Host/QEMU scheduling | read-only condition drift | CPU pinning, governor 고정, poller `perf` profiling |

상관관계를 최종 인과로 확정하지 않는다. Counter와 source가 같은 설명을 지지하면
병목 후보로 좁히고, 다음 A/B 또는 trace에서 직접 검증한다.
