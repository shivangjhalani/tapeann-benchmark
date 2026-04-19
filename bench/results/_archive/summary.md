# TAPEANN vs DiskANN — SIFT10M Benchmark Summary


## Cache mode: TAPEANN=drop_once  DiskANN=cold

### TAPEANN

| recall_target   | actual_recall   | latency_ms         | qps                | probes   |
|:----------------|:----------------|:-------------------|:-------------------|:---------|
| 90%             | 94.04%          | 1.4792333333333332 | 676.0337136853801  | 50.0     |
| 95%             | 97.16%          | 3.0719             | 325.62590272572817 | 100.0    |
| 99%             | nan             | N/A                | N/A                | N/A      |


### DiskANN

| recall_target   | actual_recall   |   latency_ms |     qps |   mean_ios |
|:----------------|:----------------|-------------:|--------:|-----------:|
| 90%             | 91.13%          |      2.06183 | 484.835 |    27.2762 |
| 95%             | 95.27%          |      1.31542 | 759.793 |    47.78   |
| 99%             | 99.24%          |      7.67591 | 130.263 |   105.973  |



## Cache mode: TAPEANN=cache  DiskANN=warm

### TAPEANN

| recall_target   | actual_recall   | latency_ms   | qps                | probes   |
|:----------------|:----------------|:-------------|:-------------------|:---------|
| 90%             | 94.04%          | 1.4546       | 687.489250059314   | 50.0     |
| 95%             | 97.16%          | 3.0191       | 331.26205005917404 | 100.0    |
| 99%             | nan             | N/A          | N/A                | N/A      |


### DiskANN

| recall_target   | actual_recall   |   latency_ms |      qps |   mean_ios |
|:----------------|:----------------|-------------:|---------:|-----------:|
| 90%             | 91.13%          |     1.69465  |  589.839 |    27.2762 |
| 95%             | 95.27%          |     0.992173 | 1007.16  |    47.78   |
| 99%             | 99.24%          |     7.15041  |  139.835 |   105.973  |



## Notes

- TAPEANN is single-threaded. DiskANN run with `-T 1` for apples-to-apples.
  DiskANN's real multi-thread QPS is significantly higher.
- Cold runs: `sync && echo 3 > /proc/sys/vm/drop_caches` before each run, then
  queries are issued (page cache warms during the run). Both TAPEANN drop_once and
  DiskANN cold use this methodology. TAPEANN direct (O_DIRECT every query) is shown
  in plots for reference but is a stricter / different cold model.
- DiskANN recall ceiling may be <1.0 due to PQ compression at the chosen `-B` budget.
- Ground truth computed via FAISS `IndexFlatL2` on float32 base vectors.
- SIFT10M = first 10M vectors of BIGANN (`bigann_base.bvecs`).
