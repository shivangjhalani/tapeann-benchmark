# TapeANN RAM vs. Bare Metal Benchmark

This folder contains a modified version of the SIFT10M TapeANN benchmark designed to demonstrate the difference between architectural efficiency and OS-level caching.

## Key Differences

1.  **Page Cache Support**: The benchmark can now be run without `O_DIRECT`, allowing the Linux kernel to cache the `index_tape.bin` file in RAM.
2.  **Warm-up Pass**: When running in cache mode, the benchmark performs a 1000-query warm-up pass. This ensures that the relevant parts of the 1.8GB index are pulled into the Linux page cache before timing begins.
3.  **Performance Comparison**: By comparing the "Cached Latency" vs "O_DIRECT Latency", we can see how much of TapeANN's speed comes from clever I/O patterns versus simply having the data in RAM.

## Execution Order

Follow these steps in the exact sequence to prepare the data properly:

1.  **`python split_dataset.py`**: Extracts the disjoint base and query sets from the raw `.mat` file.
2.  **`python export_test.py`**: Computes the 100% exact ground truth and prepares `test_queries.bin`.
3.  **`python tape_writer.py`**: Trains the FAISS router, builds the index tape (`index_tape.bin`), and exports centroids/means.
4.  **`g++ benchmark_search.cpp -o benchmark_search -O3 -march=native -luring`**: Compiles the search implementation.
5.  **`./benchmark_search --cache`** or **`./benchmark_search --direct`**: Runs the performance benchmark.

## Compilation

```bash
g++ benchmark_search.cpp -o benchmark_search -O3 -march=native -luring
```

## Running Benchmarks

### 1. Linux Page Cache (The "Easy" Way)
This mode uses the Linux page cache. It is "fast" because the data is eventually served from RAM.
```bash
./benchmark_search --cache
```

### 2. O_DIRECT Bare Metal (The "Honest" Way)
This mode bypasses the Linux page cache entirely, forcing every read to go directly to the SSD (or at least the controller). This demonstrates the true architectural performance of TapeANN.
```bash
./benchmark_search --direct
```

## Why this matters?
In a real-world scenario with datasets much larger than RAM (e.g., 100B+ vectors), you cannot rely on the page cache. TapeANN is designed to be fast even when the data *must* come from disk. This benchmark quantifies the "cache tax" or "RAM advantage".
