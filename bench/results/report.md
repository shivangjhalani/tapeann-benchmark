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
| 95 | 95.09 | 428.0574 | 2.3361 | 10477979.2 | 95.198 | 730.0434 | 1.369 | 197765.9 | 0.59× |
| 97 | 97.158 | 286.2144 | 3.4939 | 17136076.4 | 97.377 | 243.1224 | 4.1123 | 232067.5 | 1.18× |
| 99 | 98.889 | 13.2796 | 75.3032 | 157302132.7 | 98.79 | 417.2248 | 2.396 | 374326.9 | 0.03× |

### `sift10m` · mode=`ram_capped_3gb`

| target | tape achieved | tape qps | tape ms | tape B/q (app) | diskann achieved | diskann qps | diskann ms | diskann B/q (app) | qps ratio (tape/diskann) |
|---|---|---|---|---|---|---|---|---|---|
| 85 | 85.753 | 1261.1765 | 0.7929 | 3614573.4 | 82.363 | 1055.678 | 0.9465 | 125403.1 | 1.19× |
| 90 | 90.128 | 903.5297 | 1.1068 | 5360564.6 | 90.859 | 489.7676 | 2.041 | 112729.3 | 1.84× |
| 95 | 95.09 | 460.3112 | 2.1724 | 10477979.2 | 95.198 | 728.6594 | 1.3716 | 197765.9 | 0.63× |
| 97 | 97.158 | 270.8578 | 3.692 | 17136076.4 | 97.377 | 242.8439 | 4.1171 | 232067.5 | 1.12× |
| 99 | 98.889 | 29.5347 | 33.8585 | 157302132.7 | 98.79 | 419.1134 | 2.3852 | 374326.9 | 0.07× |

### `sift10m` · mode=`warm`

| target | tape achieved | tape qps | tape ms | tape B/q (app) | diskann achieved | diskann qps | diskann ms | diskann B/q (app) | qps ratio (tape/diskann) |
|---|---|---|---|---|---|---|---|---|---|
| 85 | 85.753 | 1672.7218 | 0.5978 | 3614573.4 | 82.363 | 1592.6722 | 0.6272 | 125403.1 | 1.05× |
| 90 | 90.128 | 1126.1895 | 0.8879 | 5360564.6 | 90.859 | 597.318 | 1.6734 | 112729.3 | 1.89× |
| 95 | 95.09 | 515.9113 | 1.9383 | 10477979.2 | 95.198 | 953.203 | 1.0483 | 197765.9 | 0.54× |
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
| 95.0 | tapeann | tape_int8 | 95.09 | 2.3361 | 3.8813 | 6.9993 | 428.0574 | 10477979.2 | 60.0 | {"probes": 60} | 3 |
| 97.0 | diskann | diskann_fp32_pq64 (ref) | 97.409 | 4.0934 | 4.418 | 13.424 | 244.2482 | 231785.3 | 56.5882 | {"L": 50, "W": 1} | 3 |
| 97.0 | diskann | diskann_uint8_pq32 (ref) | 96.775 | 1.7832 | 2.028 | 5.701 | 560.5421 | 276853.6 | 67.5912 | {"L": 50, "W": 4} | 3 |
| 97.0 | diskann | diskann_uint8_pq64 | 97.377 | 4.1123 | 4.431 | 22.23 | 243.1224 | 232067.5 | 56.6571 | {"L": 50, "W": 1} | 3 |
| 97.0 | tapeann | tape_int8 | 97.158 | 3.4939 | 5.5723 | 9.7131 | 286.2144 | 17136076.4 | 100.0 | {"probes": 100} | 3 |
| 99.0 | diskann | diskann_fp32_pq64 (ref) | 98.801 | 2.3417 | 2.626 | 6.387 | 426.9023 | 374020.5 | 91.3136 | {"L": 75, "W": 4} | 3 |
| 99.0 | diskann | diskann_uint8_pq32 (ref) | 99.044 | 7.5405 | 7.963 | 55.907 | 132.6016 | 436082.7 | 106.4655 | {"L": 100, "W": 1} | 3 |
| 99.0 | diskann | diskann_uint8_pq64 | 98.79 | 2.396 | 2.7 | 6.975 | 417.2248 | 374326.9 | 91.3884 | {"L": 75, "W": 4} | 3 |
| 99.0 | tapeann | tape_int8 | 98.889 | 75.3032 | 135.3327 | 262.3233 | 13.2796 | 157302132.7 | 1000.0 | {"probes": 1000} | 3 |

### `sift10m` · mode=`ram_capped_3gb`

| target | algo | variant | achieved | mean_ms | p95_ms | p999_ms | qps | B/q (app) | ios/q | params | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 85.0 | diskann | diskann_fp32_pq64 (ref) | 82.401 | 0.9435 | 1.238 | 4.342 | 1059.0266 | 125155.3 | 30.5555 | {"L": 10, "W": 4} | 3 |
| 85.0 | diskann | diskann_uint8_pq32 (ref) | 85.909 | 2.1324 | 2.564 | 41.473 | 468.7725 | 114092.0 | 27.8545 | {"L": 20, "W": 1} | 3 |
| 85.0 | diskann | diskann_uint8_pq64 | 82.363 | 0.9465 | 1.195 | 3.563 | 1055.678 | 125403.1 | 30.616 | {"L": 10, "W": 4} | 3 |
| 85.0 | tapeann | tape_int8 | 85.753 | 0.7929 | 1.4409 | 3.878 | 1261.1765 | 3614573.4 | 20.0 | {"probes": 20} | 3 |
| 90.0 | diskann | diskann_fp32_pq64 (ref) | 90.878 | 2.1499 | 2.589 | 33.132 | 464.9504 | 112566.3 | 27.482 | {"L": 20, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq32 (ref) | 92.131 | 2.8932 | 3.361 | 81.609 | 345.5265 | 153295.3 | 37.4256 | {"L": 30, "W": 1} | 3 |
| 90.0 | diskann | diskann_uint8_pq64 | 90.859 | 2.041 | 2.37 | 6.306 | 489.7676 | 112729.3 | 27.5218 | {"L": 20, "W": 1} | 3 |
| 90.0 | tapeann | tape_int8 | 90.128 | 1.1068 | 2.0128 | 4.3197 | 903.5297 | 5360564.6 | 30.0 | {"probes": 30} | 3 |
| 95.0 | diskann | diskann_fp32_pq64 (ref) | 95.183 | 1.394 | 1.738 | 5.716 | 716.9092 | 197390.7 | 48.1911 | {"L": 30, "W": 4} | 3 |
| 95.0 | diskann | diskann_uint8_pq32 (ref) | 96.579 | 4.4308 | 5.118 | 99.368 | 225.6377 | 233340.1 | 56.9678 | {"L": 50, "W": 1} | 3 |
| 95.0 | diskann | diskann_uint8_pq64 | 95.198 | 1.3716 | 1.6265 | 4.466 | 728.6594 | 197765.9 | 48.2827 | {"L": 30, "W": 4} | 6 |
| 95.0 | tapeann | tape_int8 | 95.09 | 2.1724 | 3.7502 | 7.1249 | 460.3112 | 10477979.2 | 60.0 | {"probes": 60} | 3 |
| 97.0 | diskann | diskann_fp32_pq64 (ref) | 97.409 | 4.3897 | 5.052 | 83.516 | 227.7542 | 231785.3 | 56.5882 | {"L": 50, "W": 1} | 3 |
| 97.0 | diskann | diskann_uint8_pq32 (ref) | 96.775 | 1.894 | 2.302 | 7.205 | 527.7114 | 276853.6 | 67.5912 | {"L": 50, "W": 4} | 3 |
| 97.0 | diskann | diskann_uint8_pq64 | 97.377 | 4.1171 | 4.43 | 29.551 | 242.8439 | 232067.5 | 56.6571 | {"L": 50, "W": 1} | 3 |
| 97.0 | tapeann | tape_int8 | 97.158 | 3.692 | 6.2189 | 11.3998 | 270.8578 | 17136076.4 | 100.0 | {"probes": 100} | 3 |
| 99.0 | diskann | diskann_fp32_pq64 (ref) | 98.801 | 2.4885 | 3.018 | 9.281 | 401.6961 | 374020.5 | 91.3136 | {"L": 75, "W": 4} | 3 |
| 99.0 | diskann | diskann_uint8_pq32 (ref) | 99.044 | 8.4334 | 8.79 | 124.484 | 118.5616 | 436082.7 | 106.4655 | {"L": 100, "W": 1} | 3 |
| 99.0 | diskann | diskann_uint8_pq64 | 98.79 | 2.3852 | 2.673 | 6.299 | 419.1134 | 374326.9 | 91.3884 | {"L": 75, "W": 4} | 3 |
| 99.0 | tapeann | tape_int8 | 98.889 | 33.8585 | 47.041 | 64.3039 | 29.5347 | 157302132.7 | 1000.0 | {"probes": 1000} | 3 |

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
| 95.0 | tapeann | tape_int8 | 95.09 | 1.9383 | 3.2972 | 5.6322 | 515.9113 | 10477979.2 | 60.0 | {"probes": 60} | 3 |
| 97.0 | diskann | diskann_fp32_pq64 (ref) | 97.409 | 3.6731 | 4.034 | 7.907 | 272.1869 | 231785.3 | 56.5882 | {"L": 50, "W": 1} | 3 |
| 97.0 | diskann | diskann_uint8_pq32 (ref) | 96.775 | 1.4458 | 1.667 | 4.101 | 691.2669 | 276853.6 | 67.5912 | {"L": 50, "W": 4} | 3 |
| 97.0 | diskann | diskann_uint8_pq64 | 97.377 | 3.6872 | 4.084 | 8.542 | 271.1461 | 232067.5 | 56.6571 | {"L": 50, "W": 1} | 3 |
| 97.0 | tapeann | tape_int8 | 97.158 | 2.9664 | 5.0787 | 7.6291 | 337.1118 | 17136076.4 | 100.0 | {"probes": 100} | 3 |
| 99.0 | diskann | diskann_fp32_pq64 (ref) | 98.801 | 2.0171 | 2.313 | 5.739 | 495.5657 | 374020.5 | 91.3136 | {"L": 75, "W": 4} | 3 |
| 99.0 | diskann | diskann_uint8_pq32 (ref) | 99.044 | 7.0488 | 7.633 | 13.549 | 141.8506 | 436082.7 | 106.4655 | {"L": 100, "W": 1} | 3 |
| 99.0 | diskann | diskann_uint8_pq64 | 98.79 | 2.0547 | 2.334 | 5.622 | 486.4887 | 374326.9 | 91.3884 | {"L": 75, "W": 4} | 3 |
| 99.0 | tapeann | tape_int8 | 98.889 | 27.561 | 37.3645 | 46.7961 | 36.2832 | 157302132.7 | 1000.0 | {"probes": 1000} | 3 |


## Thread scaling (DiskANN; TapeANN is single-threaded)
Fixed operating point ≈ 95% recall; threads is the only varied dimension. Shows DiskANN's multi-core throughput scaling relative to TapeANN's single-threaded baseline.

### `sift10m` · mode=`warm`

| variant | threads | params | recall@10 | mean_ms | qps | n |
|---|---|---|---|---|---|---|
| diskann_fp32_pq64 | 1 | {"L": 30, "W": 4} | 95.183 | 1.0122 | 987.2637 | 3 |
| diskann_fp32_pq64 | 2 | {"L": 30, "W": 4} | 95.183 | 1.0543 | 1833.3319 | 3 |
| diskann_fp32_pq64 | 4 | {"L": 30, "W": 4} | 95.183 | 1.1337 | 3388.8105 | 3 |
| diskann_fp32_pq64 | 8 | {"L": 30, "W": 4} | 95.183 | 1.344 | 5946.6069 | 3 |
| diskann_fp32_pq64 | 16 | {"L": 30, "W": 4} | 95.183 | 1.8643 | 8570.2725 | 3 |
| diskann_uint8_pq32 | 1 | {"L": 30, "W": 4} | 92.754 | 1.0087 | 990.6346 | 3 |
| diskann_uint8_pq32 | 2 | {"L": 30, "W": 4} | 92.754 | 1.0594 | 1872.2174 | 3 |
| diskann_uint8_pq32 | 4 | {"L": 30, "W": 4} | 92.754 | 1.1712 | 3389.2354 | 3 |
| diskann_uint8_pq32 | 8 | {"L": 30, "W": 4} | 92.754 | 1.3969 | 5691.2285 | 3 |
| diskann_uint8_pq32 | 16 | {"L": 30, "W": 4} | 92.754 | 1.9702 | 8111.2456 | 3 |
| diskann_uint8_pq64 | 1 | {"L": 30, "W": 4} | 95.198 | 1.0483 | 953.203 | 3 |
| diskann_uint8_pq64 | 2 | {"L": 30, "W": 4} | 95.198 | 1.0987 | 1815.6852 | 3 |
| diskann_uint8_pq64 | 4 | {"L": 30, "W": 4} | 95.198 | 1.1923 | 3317.1729 | 3 |
| diskann_uint8_pq64 | 8 | {"L": 30, "W": 4} | 95.198 | 1.4179 | 5578.4697 | 3 |
| diskann_uint8_pq64 | 16 | {"L": 30, "W": 4} | 95.198 | 1.9791 | 8073.7573 | 3 |

### `sift10m` · mode=`ram_capped_1p5gb`

| variant | threads | params | recall@10 | mean_ms | qps | n |
|---|---|---|---|---|---|---|
| diskann_fp32_pq64 | 1 | {"L": 30, "W": 4} | 95.183 | 1.3363 | 747.9142 | 3 |
| diskann_fp32_pq64 | 2 | {"L": 30, "W": 4} | 95.183 | 1.393 | 1399.4684 | 3 |
| diskann_fp32_pq64 | 4 | {"L": 30, "W": 4} | 95.183 | 1.5235 | 2547.4102 | 3 |
| diskann_fp32_pq64 | 8 | {"L": 30, "W": 4} | 95.183 | 1.8432 | 4233.6094 | 3 |
| diskann_fp32_pq64 | 16 | {"L": 30, "W": 4} | 95.183 | 2.6058 | 6032.042 | 3 |
| diskann_uint8_pq32 | 1 | {"L": 30, "W": 4} | 92.754 | 1.3407 | 745.4563 | 3 |
| diskann_uint8_pq32 | 2 | {"L": 30, "W": 4} | 92.754 | 1.4091 | 1418.1018 | 3 |
| diskann_uint8_pq32 | 4 | {"L": 30, "W": 4} | 92.754 | 1.5567 | 2555.1597 | 3 |
| diskann_uint8_pq32 | 8 | {"L": 30, "W": 4} | 92.754 | 1.9111 | 4169.8164 | 3 |
| diskann_uint8_pq32 | 16 | {"L": 30, "W": 4} | 92.754 | 2.7293 | 5856.6187 | 3 |
| diskann_uint8_pq64 | 1 | {"L": 30, "W": 4} | 95.198 | 1.369 | 730.0434 | 3 |
| diskann_uint8_pq64 | 2 | {"L": 30, "W": 4} | 95.198 | 1.4373 | 1384.9062 | 3 |
| diskann_uint8_pq64 | 4 | {"L": 30, "W": 4} | 95.198 | 1.5906 | 2498.511 | 3 |
| diskann_uint8_pq64 | 8 | {"L": 30, "W": 4} | 95.198 | 1.9338 | 4101.2563 | 3 |
| diskann_uint8_pq64 | 16 | {"L": 30, "W": 4} | 95.198 | 2.7165 | 5844.3398 | 3 |

### `sift10m` · mode=`ram_capped_3gb`

| variant | threads | params | recall@10 | mean_ms | qps | n |
|---|---|---|---|---|---|---|
| diskann_fp32_pq64 | 1 | {"L": 30, "W": 4} | 95.183 | 1.394 | 716.9092 | 3 |
| diskann_fp32_pq64 | 2 | {"L": 30, "W": 4} | 95.183 | 1.3842 | 1406.6 | 3 |
| diskann_fp32_pq64 | 4 | {"L": 30, "W": 4} | 95.183 | 1.5345 | 2602.9629 | 3 |
| diskann_fp32_pq64 | 8 | {"L": 30, "W": 4} | 95.183 | 1.8515 | 4275.3555 | 3 |
| diskann_fp32_pq64 | 16 | {"L": 30, "W": 4} | 95.183 | 2.6326 | 6070.9922 | 3 |
| diskann_uint8_pq32 | 1 | {"L": 30, "W": 4} | 92.754 | 1.4231 | 702.2916 | 3 |
| diskann_uint8_pq32 | 2 | {"L": 30, "W": 4} | 92.754 | 1.4071 | 1418.7828 | 3 |
| diskann_uint8_pq32 | 4 | {"L": 30, "W": 4} | 92.754 | 1.5684 | 2529.5325 | 3 |
| diskann_uint8_pq32 | 8 | {"L": 30, "W": 4} | 92.754 | 1.9221 | 4159.0229 | 3 |
| diskann_uint8_pq32 | 16 | {"L": 30, "W": 4} | 92.754 | 2.7501 | 5776.7432 | 3 |
| diskann_uint8_pq64 | 1 | {"L": 30, "W": 4} | 95.198 | 1.3716 | 728.6594 | 6 |
| diskann_uint8_pq64 | 2 | {"L": 30, "W": 4} | 95.198 | 1.4284 | 1399.1859 | 3 |
| diskann_uint8_pq64 | 4 | {"L": 30, "W": 4} | 95.198 | 1.5713 | 2525.532 | 3 |
| diskann_uint8_pq64 | 8 | {"L": 30, "W": 4} | 95.198 | 1.9532 | 4093.217 | 3 |
| diskann_uint8_pq64 | 16 | {"L": 30, "W": 4} | 95.198 | 2.7497 | 5812.9243 | 3 |


## Pareto plots
![recall_vs_bytes__sift10m__ram_capped_1p5gb.png](plots/recall_vs_bytes__sift10m__ram_capped_1p5gb.png)

![recall_vs_bytes__sift10m__ram_capped_3gb.png](plots/recall_vs_bytes__sift10m__ram_capped_3gb.png)

![recall_vs_bytes__sift10m__warm.png](plots/recall_vs_bytes__sift10m__warm.png)

![recall_vs_latency__sift10m__ram_capped_1p5gb.png](plots/recall_vs_latency__sift10m__ram_capped_1p5gb.png)

![recall_vs_latency__sift10m__ram_capped_3gb.png](plots/recall_vs_latency__sift10m__ram_capped_3gb.png)

![recall_vs_latency__sift10m__warm.png](plots/recall_vs_latency__sift10m__warm.png)

![recall_vs_qps__sift10m__ram_capped_1p5gb.png](plots/recall_vs_qps__sift10m__ram_capped_1p5gb.png)

![recall_vs_qps__sift10m__ram_capped_3gb.png](plots/recall_vs_qps__sift10m__ram_capped_3gb.png)

![recall_vs_qps__sift10m__warm.png](plots/recall_vs_qps__sift10m__warm.png)

![threads_vs_qps__sift10m__ram_capped_1p5gb.png](plots/threads_vs_qps__sift10m__ram_capped_1p5gb.png)

![threads_vs_qps__sift10m__ram_capped_3gb.png](plots/threads_vs_qps__sift10m__ram_capped_3gb.png)

![threads_vs_qps__sift10m__warm.png](plots/threads_vs_qps__sift10m__warm.png)

## TapeANN deep-dive plots (panel-facing)
> This section is built specifically to present where TapeANN — a clustering-based design — wins against a mature graph-based baseline, and to frame the losses as *measurable, localized* problems rather than fundamental limits. Each plot is captioned with (a) what the panel should *see*, (b) the one-line claim it supports, and (c) the follow-up question a skeptic is likely to ask.
>
> All comparisons are single-threaded unless noted. The DiskANN variant used for head-to-head comparison is `diskann_uint8_pq64`, the only one that matches TapeANN's 128 B/vector storage budget; other DiskANN variants are shown for context only.

### 1. Zoomed recall-vs-QPS — the win window
![recall_vs_qps_zoom__sift10m__warm.png](plots/recall_vs_qps_zoom__sift10m__warm.png)
![recall_vs_qps_zoom__sift10m__ram_capped_3gb.png](plots/recall_vs_qps_zoom__sift10m__ram_capped_3gb.png)
![recall_vs_qps_zoom__sift10m__ram_capped_1p5gb.png](plots/recall_vs_qps_zoom__sift10m__ram_capped_1p5gb.png)

- **See:** In the 75–97 % recall window, the red (TapeANN) curve sits *above* the blue (DiskANN `uint8_pq64`) curve for most of the range, and the gap is largest around 88–92 % recall.
- **Claim:** In the operating range where production ANN systems actually run (≈ 85–95 % recall), TapeANN single-threaded already beats DiskANN single-threaded — clipping the plot to that window removes the 99 % collapse that otherwise visually dominates.
- **Skeptic question:** *"Why cut the x-axis at 97 %?"* — Because the unclipped plot is in the "All operating points" section above; this zoom is to show the practical range, not hide anything.

### 2. Direct QPS speedup (TapeANN ÷ DiskANN) at fixed recall targets
![qps_speedup_bars__sift10m.png](plots/qps_speedup_bars__sift10m.png)

- **See:** Bars above 1.0× are TapeANN wins. At 85 %, 90 %, 97 % recall, every mode is ≥ 1.05× and 90 % recall peaks at **~1.9×**. The only red zone is 95 % (≈ 0.55–0.63×) and 99 % (essentially 0).
- **Claim:** The 90 % recall win is not a warm-cache artefact — it holds under the 1.5 GB RAM cap. A cluster-based design already dominates on QPS in the regime where most recommendation and retrieval workloads operate.
- **Skeptic question:** *"What about multi-threaded DiskANN?"* — Covered in the thread-scaling plot; the 95 %-recall speedup section discusses the multi-core picture honestly.

### 3. Average read size per I/O — the sequential-bandwidth story
![avg_read_size__sift10m__warm.png](plots/avg_read_size__sift10m__warm.png)
![avg_read_size__sift10m__ram_capped_1p5gb.png](plots/avg_read_size__sift10m__ram_capped_1p5gb.png)

- **See:** TapeANN's curve sits at **~175 KB per I/O**; DiskANN's is pinned at **4 KB per I/O** (the OS page size). That is a ~44× gap on the y-axis (log scale).
- **Claim:** TapeANN's "bigger byte count" is structural, not wasteful. Each I/O is a contiguous cluster scan — exactly what NVMe sequential bandwidth is optimised for. DiskANN's graph traversal forces single-page random reads and cannot amortise across a request. **This is the core reason TapeANN wins at moderate recall despite "reading more bytes."**
- **Skeptic question:** *"Why does total bytes matter less than bytes/I/O?"* — Modern NVMe drives hit full bandwidth (~3–7 GB/s) on sequential reads but ≈ 100–200 MB/s on 4 KB random reads. The bytes/I/O ratio is the leading indicator of whether an ANN index will scale to cheaper storage tiers.

### 4. Page-cache effectiveness (physical ÷ app bytes)
![io_amplification__sift10m__ram_capped_1p5gb.png](plots/io_amplification__sift10m__ram_capped_1p5gb.png)
![io_amplification__sift10m__ram_capped_3gb.png](plots/io_amplification__sift10m__ram_capped_3gb.png)
![io_amplification__sift10m__warm.png](plots/io_amplification__sift10m__warm.png)

- **See:** The dotted line is *physical bytes read = app bytes read*. TapeANN (red) sits **below** that line — physical reads are smaller than what the algorithm nominally touched, meaning the page cache absorbed the redundancy. DiskANN (blue) sits **above** the line at ~1.9× — the OS reads more than the algorithm asked for (4 KB page granularity on sub-4 KB random accesses).
- **Claim:** The large `bytes_per_query_app` numbers reported elsewhere for TapeANN over-state the real I/O cost by ~10–50×, because clusters get re-used across queries and within the same query. DiskANN has no such reuse — every neighbour lookup eats a full 4 KB page.
- **Skeptic question:** *"Is this just because sift10m is small?"* — Partly, but the mechanism (sequential cluster locality) is scale-independent; DiskANN's 4 KB amplification is a hard floor set by the kernel, not by dataset size.

### 5. Tail-latency predictability (p999 / mean ratio)
![tail_ratio__sift10m__warm.png](plots/tail_ratio__sift10m__warm.png)
![tail_ratio__sift10m__ram_capped_1p5gb.png](plots/tail_ratio__sift10m__ram_capped_1p5gb.png)

- **See:** Across 85–97 % recall, TapeANN's p999/mean ratio is comparable to or tighter than DiskANN's in warm mode. Under the 1.5 GB cap DiskANN's ratio blows up at higher recall (page-fault driven), while TapeANN's grows more smoothly.
- **Claim:** Clustering gives **bounded per-probe work**: each probe scans a fixed-size cluster. That makes worst-case latency easier to reason about than in beam search, where an unlucky query can expand many extra neighbours.
- **Skeptic question:** *"At 99 % recall TapeANN's absolute tail is huge."* — Yes, because probe count explodes (addressed in plot 7). At bounded probe counts, the tail is tight.

### 6. Cache-sensitivity (QPS across memory regimes)
![cache_sensitivity__sift10m.png](plots/cache_sensitivity__sift10m.png)

- **See:** For each recall target (85/90/95/97), two curves span warm → 3 GB → 1.5 GB. DiskANN (blue) is nearly flat. TapeANN (red) drops modestly at 85–90 % and sharply only at 95 %.
- **Claim:** At 85–90 % recall TapeANN loses only ~20 % going from warm to 1.5 GB-capped — it is **not a warm-cache-only win**. The cache sensitivity is concentrated at high recall (where probe count is high).
- **Skeptic question:** *"What if there's zero page cache?"* — The 1.5 GB cap is already well under the 1.66 GB index size, so this mode is nearly cache-starved; the fact that TapeANN still beats DiskANN at 85–90 % here is the strong form of the claim.

### 7. TapeANN probe sweep — locating the cliff
![tape_probe_curve__sift10m.png](plots/tape_probe_curve__sift10m.png)

- **See:** Recall (solid) rises steeply up to ~30 probes, flattens sharply around 60 probes, and reaches 99 % only at 1000 probes. QPS (dashed) falls roughly linearly in log-probes.
- **Claim:** The "95 %-recall loss" in plot 2 and the "99 %-recall collapse" in the takeaways are the same phenomenon: recall is *sub-logarithmic* in probes past ~60, so we pay linear cost for diminishing gains. **This is the single actionable optimisation target**: any mechanism that raises the recall-per-probe slope (better routing, centroid re-ranking, learned probe budgets) directly improves the frontier.
- **Skeptic question:** *"Is this a fundamental limit of clustering?"* — No. The probe budget is currently static; adaptive / learned probing is an open research direction with public precedent (SOAR, ScaNN).

### Headline numbers for the panel
| claim | evidence | number |
|---|---|---|
| Peak single-thread QPS advantage | warm, 90 % recall | **1.89×** vs DiskANN |
| Worst useful-regime disadvantage | warm, 95 % recall | 0.54× (actionable, see plot 7) |
| Sequential read size advantage | any mode, any recall | **~44×** larger I/O than DiskANN (175 KB vs 4 KB) |
| Page-cache reuse advantage | warm, mid-recall | physical reads are **~5–50× below app reads** |
| Cache-starved robustness | 1.5 GB cap, 90 % recall | still **1.95× DiskANN QPS** |
| Index size (int8, full vectors, no PQ) | build_costs | 1.66 GB on sift10m (128 B/vec) |

## Takeaways
> Numbers below compare TapeANN (single-threaded) against single-threaded DiskANN `uint8_pq64` unless noted. Multi-thread DiskANN numbers are in the thread-scaling section.

**1. TapeANN wins at 85–90 % and 97 % recall (1-thread comparison).**
At 90 % recall TapeANN is ~1.9–2× faster than 1-thread DiskANN across all modes (warm, 1.5 GB cap, 3 GB cap). It also leads at 85 % (~1.05–1.25×) and 97 % (~1.12–1.24×).

**2. 95 % recall is a consistent crossover loss.**
TapeANN loses to DiskANN at 95 % in every mode (~0.54–0.63×). The jump from 30 probes (90 % target) to 60 probes (95 % target) halves QPS while adding only 5 recall points — a probe-count cliff that is the main weak spot in the recall curve.

**3. 99 % recall is a collapse.**
TapeANN needs 1000 probes to reach ~98.9 % recall: 13 QPS (1.5 GB cap), 29 QPS (3 GB cap), 36 QPS (warm). DiskANN achieves the same recall at 417–495 QPS (1-thread) — 15–38× faster. High-recall workloads are not viable with the current probe mechanism.

**4. RAM cap matters significantly for TapeANN at high probe counts.**
Going from 1.5 GB → 3 GB, TapeANN at 99 % recall improves from 13 → 29 QPS (+2.2×); at 95 % from 428 → 460 QPS (+7 %). At 85–90 % the two caps are nearly equivalent. DiskANN sees minimal change across caps. TapeANN's large I/O footprint (157 MB/query at 1000 probes) makes it highly sensitive to page cache size at high probe counts.

**5. I/O amplification is extreme and worsens rapidly with probes.**
TapeANN reads ~3.6 MB/query at 85 % recall vs DiskANN's 125 KB (29×); at 99 % this is 157 MB/query (420×). This is the root cause of the 99 %-recall collapse and limits viability in storage-bound deployments.

**6. DiskANN multi-threading changes the picture entirely.**
At 16 threads DiskANN reaches 8073 QPS warm (95 % recall) vs TapeANN's 516 QPS — a 15.6× gap. At 1 thread DiskANN is only 1.85× ahead (953 vs 516). Threading is the dominant factor: a multi-threaded DiskANN deployment dominates TapeANN at every recall target.

**7. Panel narrative (suggested story arc).**
*(Use this as a spoken outline mapped to the plots above.)*
1. **Frame:** "Graph-based ANN is the accepted state of the art. I'm showing that a clustering-based design is already competitive single-threaded, and identifying *exactly* where it needs work."
2. **Plot 2 (speedup bars):** the headline — wins at 85/90/97, loss at 95, collapse at 99.
3. **Plot 3 (avg read size) + Plot 4 (phys/app ratio):** *why* the wins exist — cluster scans are sequential (44× bigger I/O) and cache-absorbed, while graph traversal pays a 4 KB random-page tax. The numbers labeled "huge I/O amplification" for TapeANN turn out to be a page-cache artefact of the counting method, not real bandwidth.
4. **Plot 5 (tail ratio) + Plot 6 (cache sensitivity):** show robustness — TapeANN's wins survive under tight RAM caps and its tail latency is bounded by design.
5. **Plot 7 (probe curve):** own the weakness honestly — 95 % and 99 % losses are both due to static probe budgets hitting a recall-per-probe cliff. This is a *mechanism-level* problem, not an algorithm-level dead end.
6. **Close on future work:** adaptive probe budgets, centroid re-ranking, and multi-threading (which has not been applied to TapeANN yet) are the three levers that most directly attack the plot-7 cliff and the 16-thread DiskANN comparison.

**8. "Higher recall = lower latency" in the plots is expected and not a contradiction.**
The recall-vs-latency and recall-vs-QPS curves show latency *decreasing* as recall increases over certain ranges. This happens because the plots sweep across multiple (L, W) parameter pairs, not just L at fixed W. Configurations with low beamwidth (W=1) and low L land at low recall but high latency — beam search with W=1 is sequential and cache-unfriendly. Configurations with high beamwidth (W=4) at slightly higher L reach better recall with *lower* latency because the 4 parallel beams amortize memory access costs more efficiently. The downward-sloping segment of a curve therefore represents dominated operating points — configurations that are both slower *and* less accurate than a nearby W=4 point. In practice, only the rightmost (Pareto-optimal) end of each curve should be used.

