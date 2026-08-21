# Experiment plan

## 1. 목표

SSD I/O path의 관찰 가능한 결과를 단순 benchmark 점수가 아닌 FTL 내부 동작과 연결한다. 주요 종속변수는 total IOPS, bandwidth, read/write completion latency의 p99/p99.9, 그리고 host write 대비 GC relocation write의 비율인 interval WAF다.

## 2. 가설

- H1: 동일 block size와 queue depth에서 random write는 sequential write보다 GC relocation을 더 많이 유발하여 WAF와 tail latency가 증가한다.
- H2: 높은 queue depth는 NAND parallelism 활용으로 IOPS를 높이지만, queueing으로 p99/p99.9 latency를 증가시킬 수 있다.
- H3: page mapping은 mapping lookup overhead가 낮지만 메모리 비용이 크다. DFTL/hybrid는 mapping memory를 줄이는 대신 workload locality에 따라 latency penalty가 생길 수 있다.
- H4: 이른 GC trigger는 foreground GC의 급격한 tail spike를 완화할 수 있지만 relocation 빈도와 평균 성능에 비용을 줄 수 있다.

가설은 결론이 아니다. 반대 결과가 나오면 FEMU 구현, workload duration, preconditioning, GC 발생 횟수를 먼저 확인한다.

## 3. 독립변수

### Phase A: workload characterization

- access pattern: sequential / random
- direction: read / write / randrw 70:30 / randrw 30:70
- block size: 4 KiB / 128 KiB
- queue depth: 1 / 32

### Phase B: FTL mapping

- `page`
- `dftl` (`mapping_cache_mb=4`를 명시)
- `hybrid`

GC threshold는 75로 고정한다.

### Phase C: GC trigger

- 50
- 75
- 90

mapping은 page, high threshold는 95로 고정한다. 따라서 threshold 90도 high threshold보다 작다.

## 4. 통제변수

- FEMU revision
- host hardware, kernel, CPU governor, background process
- guest image, guest kernel, fio version, nvme-cli version
- FEMU NAND geometry 및 read/program/erase latency
- namespace size와 target fraction
- fio random seed (`randrepeat=1`, `allrandrepeat=1`)
- workload 순서와 repetition 수

각 FEMU condition을 바꿀 때 emulator를 재시작하여 DRAM-backed SSD 상태를 초기화한다.

## 5. 측정 절차

1. host readiness와 FEMU binary/device 등록을 검증한다.
2. condition에 맞는 FEMU option을 기록하고 VM을 부팅한다.
3. guest에서 namespace model과 mount 상태를 확인한다.
4. full profile은 namespace 80% 범위를 4 KiB random write로 2회 precondition한다.
5. 각 workload 전후로 SMART binary log를 수집한다.
6. workload를 3회 실행하며 fio JSON을 보존한다.
7. counter delta로 각 repetition의 interval WAF를 계산한다.
8. condition/workload별 median을 비교한다.

## 6. WAF 정의

FEMU master는 NVMe SMART log vendor-specific 영역에 다음 값을 제공한다.

- byte 192: `waf_x1000` (little-endian uint32)
- byte 200: host write pages (little-endian uint64)
- byte 208: GC relocated pages (little-endian uint64)

한 workload 구간의 WAF는 누적 WAF를 그대로 읽지 않고 다음 delta로 계산한다.

```text
interval_WAF = (delta_host_write_pages + delta_gc_write_pages)
               / delta_host_write_pages
```

read-only workload처럼 host write delta가 0이면 구간 WAF를 1.0으로 기록하되, host/GC page delta도 함께 확인한다.

## 7. 해석 순서

1. fio error와 short run 여부
2. 실제 GC 발생 여부 (`gc_write_pages > 0`)
3. IOPS와 bandwidth
4. p99/p99.9 latency
5. interval WAF
6. mapping/GC source path 또는 QEMU thread가 설명하는 병목 후보

성능 개선 주장은 throughput 하나만으로 하지 않는다. IOPS 상승과 tail latency/WAF 악화가 함께 나타나면 trade-off로 보고한다.

## 8. 타당성 위협

- FEMU는 실제 controller firmware와 NAND device를 그대로 재현하지 않는다. 결과는 emulator model 안에서의 비교다.
- 한 VM boot에서 여러 workload를 고정 순서로 수행하므로 이전 workload가 SSD state에 영향을 줄 수 있다.
- 60초 runtime이 충분한 steady state를 만들지 못할 수 있다.
- host scheduler, CPU frequency, QEMU poller contention이 NVMe latency에 섞일 수 있다.
- mixed workload의 단일 tail metric은 read/write 중 더 나쁜 방향을 사용하므로 보수적이다. 원본 direction별 값도 CSV에 남긴다.

후속 실험에서는 workload별 fresh boot, runtime 확대, CPU pinning, host-side QEMU thread profiling으로 위협을 줄인다.

