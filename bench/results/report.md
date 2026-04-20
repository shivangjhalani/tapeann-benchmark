# TAPEANN vs DiskANN — benchmark report

## Environment
```
# Environment capture  —  2026-04-19T18:30:29+05:30

## Host
hostname: worker-1
kernel:   Linux 6.8.0-107-generic x86_64 GNU/Linux

## CPU
  Architecture:                            x86_64
  CPU(s):                                  32
  Model name:                              13th Gen Intel(R) Core(TM) i9-13900
  Thread(s) per core:                      2
  Core(s) per socket:                      24
  Socket(s):                               1
  CPU max MHz:                             5600.0000
  Flags:                                   fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx pdpe1gb rdtscp lm constant_tsc art arch_perfmon pebs bts rep_good nopl xtopology nonstop_tsc cpuid aperfmperf tsc_known_freq pni pclmulqdq dtes64 monitor ds_cpl vmx smx est tm2 ssse3 sdbg fma cx16 xtpr pdcm pcid sse4_1 sse4_2 x2apic movbe popcnt tsc_deadline_timer aes xsave avx f16c rdrand lahf_lm abm 3dnowprefetch cpuid_fault epb ssbd ibrs ibpb stibp ibrs_enhanced tpr_shadow flexpriority ept vpid ept_ad fsgsbase tsc_adjust bmi1 avx2 smep bmi2 erms invpcid rdseed adx smap clflushopt clwb intel_pt sha_ni xsaveopt xsavec xgetbv1 xsaves split_lock_detect user_shstk avx_vnni dtherm ida arat pln pts hwp hwp_notify hwp_act_window hwp_epp hwp_pkg_req hfi vnmi umip pku ospke waitpkg gfni vaes vpclmulqdq tme rdpid movdiri movdir64b fsrm md_clear serialize pconfig arch_lbr ibt flush_l1d arch_capabilities ibpb_exit_to_user
  L1d cache:                               896 KiB (24 instances)
  L1i cache:                               1.3 MiB (24 instances)
  L2 cache:                                32 MiB (12 instances)
  L3 cache:                                36 MiB (1 instance)
governor: performance

## Memory
                 total        used        free      shared  buff/cache   available
  Mem:           125Gi       2.0Gi       120Gi        21Mi       3.5Gi       122Gi
  Swap:             0B          0B          0B
  THP: always madvise [never]
  swappiness: 1

## Storage
  NAME          SIZE TYPE ROTA MODEL              FSTYPE   MOUNTPOINT
  loop0           4K loop    0                    squashfs /snap/bare/5
  loop1        63.8M loop    0                    squashfs /snap/core20/2717
  loop2        63.8M loop    0                    squashfs /snap/core20/2769
  loop3          74M loop    0                    squashfs /snap/core22/2339
  loop4          74M loop    0                    squashfs /snap/core22/2411
  loop5        66.8M loop    0                    squashfs /snap/core24/1499
  loop6        66.8M loop    0                    squashfs /snap/core24/1587
  loop7       151.4M loop    0                    squashfs /snap/docker/3377
  loop8       273.5M loop    0                    squashfs /snap/firefox/8054
  loop9       273.7M loop    0                    squashfs /snap/firefox/8107
  loop10       41.3M loop    0                    squashfs /snap/gh/640
  loop11      516.2M loop    0                    squashfs /snap/gnome-42-2204/226
  loop12      606.1M loop    0                    squashfs /snap/gnome-46-2404/153
  loop13      531.4M loop    0                    squashfs /snap/gnome-42-2204/247
  loop14       91.7M loop    0                    squashfs /snap/gtk-common-themes/1535
  loop16       13.2M loop    0                    squashfs /snap/kubectl/3768
  loop17        395M loop    0                    squashfs /snap/mesa-2404/1165
  loop18       12.9M loop    0                    squashfs /snap/snap-store/1113
  loop19       12.2M loop    0                    squashfs /snap/snap-store/1216
  loop20       48.1M loop    0                    squashfs /snap/snapd/25935
  loop21       48.4M loop    0                    squashfs /snap/snapd/26382
  loop22        580K loop    0                    squashfs /snap/snapd-desktop-integration/357
  loop23        580K loop    0                    squashfs /snap/snapd-desktop-integration/361
  loop24       13.2M loop    0                    squashfs /snap/kubectl/3779
  nvme0n1     953.9G disk    0 3500 Micron 1024GB          
  ├─nvme0n1p1   285M part    0                    vfat     /boot/efi
  └─nvme0n1p2 953.6G part    0                    ext4     /

  mounts for repo path:
    Filesystem      Size  Used Avail Use% Mounted on
    /dev/nvme0n1p2  938G  802G   89G  91% /

  nvme id-ctrl /dev/nvme0n1 (truncated):
    (need sudo)

## Toolchain
  g++:    g++ (Ubuntu 12.3.0-1ubuntu1~22.04.3) 12.3.0
  python: Python 3.10.12
  rustc:  rustc 1.95.0 (59807616e 2026-04-14)
  cargo:  cargo 1.95.0 (f2d3ce0bd 2026-03-21)
  faiss:  1.13.2
  numpy:  1.26.4

## Git
  tape repo:    bb380a795cd44062da32056f57301d3566b0f422  (main)
  DiskANN repo: 20295a40afb34d4c47beb5bc66e3f30b020a1afb

## Flags used for builds
  CXXFLAGS (tape benchmark_search): -O3 -march=native -std=c++17 -luring
  RUSTFLAGS (diskann):               -Ctarget-cpu=x86-64-v3
```

## Build costs
| algo | variant | dataset | wall_s | peak_rss_mb | idx_GB | built_at |
|---|---|---|---|---|---|---|
| tapeann | tape_int8 | sift10m | 0.0 | 0.0 | 1.66 | 2026-04-19T18:30:47 |

## Head-to-head (matched bytes/vector)
`tape_int8` vs `diskann_uint8_pq64` at fixed recall targets. Both systems store 1 byte per dimension in the vector store; other DiskANN variants are reported as reference only.

### `sift10m` · mode=`ram_capped_1p5gb`

| target | tape achieved | tape qps | tape ms | tape B/q (app) | diskann achieved | diskann qps | diskann ms | diskann B/q (app) | qps ratio (tape/diskann) |
|---|---|---|---|---|---|---|---|---|---|
| 85 | 85.753 | 1328.077 | 0.753 | 3614573.4 | 82.363 | 1056.6318 | 0.9457 | 125403.1 | 1.26× |
| 90 | 90.128 | 948.5987 | 1.0542 | 5360564.6 | 90.859 | 485.7073 | 2.0581 | 112729.3 | 1.95× |
| 95 | 95.858 | 419.213 | 2.3854 | 12156692.1 | 95.198 | 730.0434 | 1.369 | 197765.9 | 0.57× |
| 97 | 97.158 | 286.2144 | 3.4939 | 17136076.4 | 97.377 | 243.1224 | 4.1123 | 232067.5 | 1.18× |
| 99 | 98.889 | 13.2796 | 75.3032 | 157302132.7 | 98.79 | 417.2248 | 2.396 | 374326.9 | 0.03× |

### `sift10m` · mode=`warm`

| target | tape achieved | tape qps | tape ms | tape B/q (app) | diskann achieved | diskann qps | diskann ms | diskann B/q (app) | qps ratio (tape/diskann) |
|---|---|---|---|---|---|---|---|---|---|
| 85 | 85.753 | 1672.7218 | 0.5978 | 3614573.4 | 82.363 | 1592.6722 | 0.6272 | 125403.1 | 1.05× |
| 90 | 90.128 | 1126.1895 | 0.8879 | 5360564.6 | 90.859 | 597.318 | 1.6734 | 112729.3 | 1.89× |
| 95 | 95.858 | 492.0813 | 2.0322 | 12156692.1 | 95.198 | 953.203 | 1.0483 | 197765.9 | 0.52× |
| 97 | 97.158 | 337.1118 | 2.9664 | 17136076.4 | 97.377 | 271.1461 | 3.6872 | 232067.5 | 1.24× |
| 99 | 98.889 | 36.2832 | 27.561 | 157302132.7 | 98.79 | 486.4887 | 2.0547 | 374326.9 | 0.07× |


## All operating points (closest to recall target)
Includes reference variants `diskann_fp32_pq64 (ref)` and `diskann_uint8_pq32 (ref)`. Each cell is the median across trials.

### `sift10m` · mode=`ram_capped_1p5gb`

| target | algo | variant | achieved | mean_ms | p95_ms | p999_ms | qps | B/q (app) | ios/q | params | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 85.0 | diskann | diskann_fp32_pq64 (ref) | 82.401 | 0.8966 | 1.128 | 3.336 | 1114.4701 | 125155.3 | 30.5555 | {"L": 10, "W": 4} | 3 |
| 85.0 | diskann | diskann_uint8_pq32 (ref) | 85.909 | 2.0288 | 2.37 | 10.311 | 492.7242 | 114092.0 | 27.8545 | {"L": 20, "W": 1} | 3 |
| 85.0 | diskann | diskann_uint8_pq64 | 82.363 | 0.9457 | 1.186 | 3.865 | 1056.6318 | 125403.1 | 30.616 | {"L": 10, "W": 4} | 3 |
| 85.0 | tapeann | tape_int8 | 85.753 | 0.753 | 1.2662 | 2.9041 | 1328.077 | 3614573.4 | 20.0 | {"probes": 20} | 3 |
| 90.0 | diskann | diskann_fp32_pq64 (ref) | 90.878 | 2.072 | 2.376 | 12.11 | 482.4553 | 112566.3 | 27.482 | {"L": 20, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq32 (ref) | 92.131 | 2.6957 | 3.006 | 11.408 | 370.8506 | 153295.3 | 37.4256 | {"L": 30, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq64 | 90.859 | 2.0581 | 2.367 | 7.745 | 485.7073 | 112729.3 | 27.5218 | {"L": 20, "W": 1} | 3 |
| 90.0 | tapeann | tape_int8 | 90.128 | 1.0542 | 1.7807 | 3.7532 | 948.5987 | 5360564.6 | 30.0 | {"probes": 30} | 3 |
| 95.0 | diskann | diskann_fp32_pq64 (ref) | 95.183 | 1.3363 | 1.596 | 4.713 | 747.9142 | 197390.7 | 48.1911 | {"L": 30, "W": 4} | 3 |
| 95.0 | diskann | diskann_uint8_pq32 (ref) | 96.579 | 4.0936 | 4.419 | 39.287 | 244.2372 | 233340.1 | 56.9678 | {"L": 50, "W": 1} | 3 |
| 95.0 | diskann | diskann_uint8_pq64 | 95.198 | 1.369 | 1.615 | 4.866 | 730.0434 | 197765.9 | 48.2827 | {"L": 30, "W": 4} | 3 |
| 95.0 | tapeann | tape_int8 | 95.858 | 2.3854 | 3.9247 | 6.9999 | 419.213 | 12156692.1 | 70.0 | {"probes": 70} | 3 |
| 97.0 | diskann | diskann_fp32_pq64 (ref) | 97.409 | 4.0934 | 4.418 | 13.424 | 244.2482 | 231785.3 | 56.5882 | {"L": 50, "W": 1} | 3 |
| 97.0 | diskann | diskann_uint8_pq32 (ref) | 96.775 | 1.7832 | 2.028 | 5.701 | 560.5421 | 276853.6 | 67.5912 | {"L": 50, "W": 4} | 3 |
| 97.0 | diskann | diskann_uint8_pq64 | 97.377 | 4.1123 | 4.431 | 22.23 | 243.1224 | 232067.5 | 56.6571 | {"L": 50, "W": 1} | 3 |
| 97.0 | tapeann | tape_int8 | 97.158 | 3.4939 | 5.5723 | 9.7131 | 286.2144 | 17136076.4 | 100.0 | {"probes": 100} | 3 |
| 99.0 | diskann | diskann_fp32_pq64 (ref) | 98.801 | 2.3417 | 2.626 | 6.387 | 426.9023 | 374020.5 | 91.3136 | {"L": 75, "W": 4} | 3 |
| 99.0 | diskann | diskann_uint8_pq32 (ref) | 99.044 | 7.5405 | 7.963 | 55.907 | 132.6016 | 436082.7 | 106.4655 | {"L": 100, "W": 1} | 3 |
| 99.0 | diskann | diskann_uint8_pq64 | 98.79 | 2.396 | 2.7 | 6.975 | 417.2248 | 374326.9 | 91.3884 | {"L": 75, "W": 4} | 3 |
| 99.0 | tapeann | tape_int8 | 98.889 | 75.3032 | 135.3327 | 262.3233 | 13.2796 | 157302132.7 | 1000.0 | {"probes": 1000} | 3 |

### `sift10m` · mode=`warm`

| target | algo | variant | achieved | mean_ms | p95_ms | p999_ms | qps | B/q (app) | ios/q | params | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 85.0 | diskann | diskann_fp32_pq64 (ref) | 82.401 | 0.5891 | 0.809 | 2.134 | 1695.3853 | 125155.3 | 30.5555 | {"L": 10, "W": 4} | 3 |
| 85.0 | diskann | diskann_uint8_pq32 (ref) | 85.909 | 1.6597 | 2.003 | 4.633 | 602.2542 | 114092.0 | 27.8545 | {"L": 20, "W": 1} | 3 |
| 85.0 | diskann | diskann_uint8_pq64 | 82.363 | 0.6272 | 0.84 | 2.334 | 1592.6722 | 125403.1 | 30.616 | {"L": 10, "W": 4} | 3 |
| 85.0 | tapeann | tape_int8 | 85.753 | 0.5978 | 1.023 | 1.7897 | 1672.7218 | 3614573.4 | 20.0 | {"probes": 20} | 3 |
| 90.0 | diskann | diskann_fp32_pq64 (ref) | 90.878 | 1.6637 | 1.999 | 4.805 | 600.7871 | 112566.3 | 27.482 | {"L": 20, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq32 (ref) | 92.131 | 2.3241 | 2.658 | 6.38 | 430.1252 | 153295.3 | 37.4256 | {"L": 30, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq64 | 90.859 | 1.6734 | 2.012 | 5.287 | 597.318 | 112729.3 | 27.5218 | {"L": 20, "W": 1} | 3 |
| 90.0 | tapeann | tape_int8 | 90.128 | 0.8879 | 1.5375 | 2.7948 | 1126.1895 | 5360564.6 | 30.0 | {"probes": 30} | 3 |
| 95.0 | diskann | diskann_fp32_pq64 (ref) | 95.183 | 1.0122 | 1.248 | 3.317 | 987.2637 | 197390.7 | 48.1911 | {"L": 30, "W": 4} | 3 |
| 95.0 | diskann | diskann_uint8_pq32 (ref) | 96.579 | 3.6792 | 4.046 | 7.835 | 271.7361 | 233340.1 | 56.9678 | {"L": 50, "W": 1} | 3 |
| 95.0 | diskann | diskann_uint8_pq64 | 95.198 | 1.0483 | 1.275 | 3.598 | 953.203 | 197765.9 | 48.2827 | {"L": 30, "W": 4} | 3 |
| 95.0 | tapeann | tape_int8 | 95.858 | 2.0322 | 3.4996 | 5.8199 | 492.0813 | 12156692.1 | 70.0 | {"probes": 70} | 3 |
| 97.0 | diskann | diskann_fp32_pq64 (ref) | 97.409 | 3.6731 | 4.034 | 7.907 | 272.1869 | 231785.3 | 56.5882 | {"L": 50, "W": 1} | 3 |
| 97.0 | diskann | diskann_uint8_pq32 (ref) | 96.775 | 1.4458 | 1.667 | 4.101 | 691.2669 | 276853.6 | 67.5912 | {"L": 50, "W": 4} | 3 |
| 97.0 | diskann | diskann_uint8_pq64 | 97.377 | 3.6872 | 4.084 | 8.542 | 271.1461 | 232067.5 | 56.6571 | {"L": 50, "W": 1} | 3 |
| 97.0 | tapeann | tape_int8 | 97.158 | 2.9664 | 5.0787 | 7.6291 | 337.1118 | 17136076.4 | 100.0 | {"probes": 100} | 3 |
| 99.0 | diskann | diskann_fp32_pq64 (ref) | 98.801 | 2.0171 | 2.313 | 5.739 | 495.5657 | 374020.5 | 91.3136 | {"L": 75, "W": 4} | 3 |
| 99.0 | diskann | diskann_uint8_pq32 (ref) | 99.044 | 7.0488 | 7.633 | 13.549 | 141.8506 | 436082.7 | 106.4655 | {"L": 100, "W": 1} | 3 |
| 99.0 | diskann | diskann_uint8_pq64 | 98.79 | 2.0547 | 2.334 | 5.622 | 486.4887 | 374326.9 | 91.3884 | {"L": 75, "W": 4} | 3 |
| 99.0 | tapeann | tape_int8 | 98.889 | 27.561 | 37.3645 | 46.7961 | 36.2832 | 157302132.7 | 1000.0 | {"probes": 1000} | 3 |


## Thread scaling (DiskANN only; TAPE is single-threaded)
Fixed operating point ≈ 95% recall; threads is the only varied dimension.

_no thread-sweep data — run `run_all.py --thread-sweep`_

## Pareto plots
![recall_vs_bytes__sift10m__ram_capped_1p5gb.png](plots/recall_vs_bytes__sift10m__ram_capped_1p5gb.png)

![recall_vs_bytes__sift10m__warm.png](plots/recall_vs_bytes__sift10m__warm.png)

![recall_vs_latency__sift10m__ram_capped_1p5gb.png](plots/recall_vs_latency__sift10m__ram_capped_1p5gb.png)

![recall_vs_latency__sift10m__warm.png](plots/recall_vs_latency__sift10m__warm.png)

![recall_vs_qps__sift10m__ram_capped_1p5gb.png](plots/recall_vs_qps__sift10m__ram_capped_1p5gb.png)

![recall_vs_qps__sift10m__warm.png](plots/recall_vs_qps__sift10m__warm.png)
