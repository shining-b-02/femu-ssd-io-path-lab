# I/O path와 측정 지점

```text
fio
  -> Linux syscall / ioengine (libaio)
  -> VFS 및 block layer
  -> blk-mq submission queue
  -> Linux nvme driver
  -> virtual PCIe/NVMe queue pair
  -> FEMU NVMe command processing / poller
  -> BBSSD FTL mapping
  -> GC victim selection 및 page relocation
  -> NAND channel/LUN timing model
  -> completion queue
  -> fio completion latency
```

## 첫 버전의 관찰값

- `fio`: IOPS, bandwidth, read/write p99와 p99.9 completion latency
- FEMU SMART vendor field: host write pages, GC relocated pages, WAF
- metadata: host/guest kernel, target model/size, condition, workload config, git revision

## 병목 후보와 판별 방법

| 후보 | 예상 신호 | 후속 확인 |
|---|---|---|
| NAND program/erase latency | write 및 GC 구간 tail latency 증가 | FEMU timing parameter 고정/변경 A/B |
| GC relocation | `gc_write_pages`와 WAF 증가, write p99 spike | GC threshold와 policy 비교 |
| mapping lookup/cache | dftl/hybrid에서 locality별 latency 차이 | mapping cache 크기 및 sequential/random 비교 |
| queueing | QD32에서 IOPS와 latency 동시 증가 | QD sweep 1/2/4/8/16/32 |
| QEMU/FEMU poller CPU | workload가 바뀌어도 host CPU가 포화 | poller thread CPU pinning과 `perf` profiling |

단순 상관관계를 원인으로 확정하지 않는다. WAF와 latency가 함께 증가하면 GC를 후보로 두고, threshold/policy A/B 및 source/trace로 확인한다.

