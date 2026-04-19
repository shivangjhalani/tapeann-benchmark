# TAPEANN vs DiskANN — SIFT10M Benchmark Summary


## Cache mode: TAPEANN=direct  DiskANN=cold

### TAPEANN

| recall_target   | actual_recall   | latency_ms   | qps                | probes   |
|:----------------|:----------------|:-------------|:-------------------|:---------|
| 90%             | 94.04%          | 2.4896       | 401.6709511568124  | 50       |
| 95%             | 97.16%          | 4.3766       | 228.48786729424668 | 100      |
| 99%             | nan             | N/A          | N/A                | N/A      |


### DiskANN

| recall_target   | actual_recall   |   latency_ms |     qps |   mean_ios |
|:----------------|:----------------|-------------:|--------:|-----------:|
| 90%             | 91.13%          |      2.06183 | 484.835 |    27.2762 |
| 95%             | 95.27%          |      1.31542 | 759.793 |    47.78   |
| 99%             | 99.24%          |      7.67591 | 130.263 |   105.973  |



## Cache mode: TAPEANN=cache  DiskANN=warm

### TAPEANN

| recall_target   | actual_recall   | latency_ms   | qps               | probes   |
|:----------------|:----------------|:-------------|:------------------|:---------|
| 90%             | 94.04%          | 1.4642       | 682.9668078131403 | 50       |
| 95%             | 97.16%          | 3.0358       | 329.4024639304302 | 100      |
| 99%             | nan             | N/A          | N/A               | N/A      |


### DiskANN

| recall_target   | actual_recall   |   latency_ms |      qps |   mean_ios |
|:----------------|:----------------|-------------:|---------:|-----------:|
| 90%             | 91.13%          |     1.69465  |  589.839 |    27.2762 |
| 95%             | 95.27%          |     0.992173 | 1007.16  |    47.78   |
| 99%             | 99.24%          |     7.15041  |  139.835 |   105.973  |



## Notes

- TAPEANN is single-threaded. DiskANN run with `-T 1` for apples-to-apples.
  DiskANN's real multi-thread QPS is significantly higher.
- Cold runs: `sync && echo 3 > /proc/sys/vm/drop_caches` before each run.
  TAPEANN uses `O_DIRECT`; DiskANN (Rust) uses io_uring — both bypass warm cache.
- DiskANN recall ceiling may be <1.0 due to PQ compression at the chosen `-B` budget.
- Ground truth computed via FAISS `IndexFlatL2` on float32 base vectors.
- SIFT10M = first 10M vectors of BIGANN (`bigann_base.bvecs`).
