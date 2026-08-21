# FEMU SSD I/O experiment report

Median values across repetitions. Mixed workloads use the worse active-direction tail latency.

| Condition | Workload | IOPS | BW (MiB/s) | p99 (us) | p99.9 (us) | WAF |
|---|---|---:|---:|---:|---:|---:|
| dftl4m-gc75 | randread-4k-qd1 | 24,142.8 | 94.3 | 52.0 | 86.5 | 1.000 |
| dftl4m-gc75 | randread-4k-qd32 | 312,512.1 | 1,220.8 | 173.1 | 216.1 | 1.000 |
| dftl4m-gc75 | randrw30-4k-qd32 | 111,558.2 | 435.8 | 831.5 | 3,719.2 | 1.027 |
| dftl4m-gc75 | randrw70-4k-qd32 | 154,825.3 | 604.8 | 700.4 | 1,056.8 | 1.028 |
| dftl4m-gc75 | randwrite-4k-qd1 | 4,322.7 | 16.9 | 411.6 | 477.2 | 1.000 |
| dftl4m-gc75 | randwrite-4k-qd32 | 98,381.9 | 384.3 | 880.6 | 3,850.2 | 1.027 |
| dftl4m-gc75 | read-128k-qd1 | 10,121.5 | 1,265.2 | 164.9 | 212.0 | 1.000 |
| dftl4m-gc75 | read-128k-qd32 | 64,051.2 | 8,006.5 | 880.6 | 1,073.2 | 1.000 |
| dftl4m-gc75 | write-128k-qd1 | 4,350.9 | 543.9 | 460.8 | 2,146.3 | 1.000 |
| dftl4m-gc75 | write-128k-qd32 | 9,580.5 | 1,197.6 | 5,210.1 | 5,406.7 | 1.000 |
| hybrid-gc75 | randread-4k-qd1 | 25,626.8 | 100.1 | 53.0 | 181.2 | 1.000 |
| hybrid-gc75 | randread-4k-qd32 | 265,944.0 | 1,038.8 | 216.1 | 284.7 | 1.000 |
| hybrid-gc75 | randrw30-4k-qd32 | 161.9 | 0.6 | 742,391.8 | 2,264,924.2 | 257.688 |
| hybrid-gc75 | randrw70-4k-qd32 | 390.8 | 1.5 | 708,837.4 | 1,132,462.1 | 258.773 |
| hybrid-gc75 | randwrite-4k-qd1 | 4.1 | 0.0 | 278,921.2 | 283,115.5 | 244.157 |
| hybrid-gc75 | randwrite-4k-qd32 | 113.5 | 0.4 | 734,003.2 | 11,878,268.9 | 255.642 |
| hybrid-gc75 | read-128k-qd1 | 18,901.1 | 2,362.6 | 56.6 | 146.4 | 1.000 |
| hybrid-gc75 | read-128k-qd32 | 61,333.2 | 7,666.7 | 970.8 | 1,187.8 | 1.000 |
| hybrid-gc75 | write-128k-qd1 | 2,094.0 | 261.8 | 2,113.5 | 2,211.8 | 1.001 |
| hybrid-gc75 | write-128k-qd32 | 2,809.2 | 351.2 | 21,102.6 | 21,102.6 | 1.001 |
| page-gc75 | randread-4k-qd1 | 26,722.4 | 104.4 | 49.4 | 58.6 | 1.000 |
| page-gc75 | randread-4k-qd32 | 308,053.4 | 1,203.3 | 166.9 | 212.0 | 1.000 |
| page-gc75 | randrw30-4k-qd32 | 176,035.2 | 687.6 | 250.9 | 3,686.4 | 1.027 |
| page-gc75 | randrw70-4k-qd32 | 248,804.9 | 971.9 | 272.4 | 391.2 | 1.027 |
| page-gc75 | randwrite-4k-qd1 | 4,774.5 | 18.7 | 226.3 | 354.3 | 1.000 |
| page-gc75 | randwrite-4k-qd32 | 145,746.3 | 569.3 | 252.9 | 3,784.7 | 1.027 |
| page-gc75 | read-128k-qd1 | 10,154.9 | 1,269.4 | 164.9 | 205.8 | 1.000 |
| page-gc75 | read-128k-qd32 | 65,952.2 | 8,244.1 | 839.7 | 1,011.7 | 1.000 |
| page-gc75 | write-128k-qd1 | 4,596.7 | 574.6 | 224.3 | 2,146.3 | 1.000 |
| page-gc75 | write-128k-qd32 | 9,622.7 | 1,202.9 | 5,210.1 | 5,275.6 | 1.000 |

## Figures

![IOPS](iops.svg)

![p99 latency](p99-latency.svg)

![Write amplification](waf.svg)
