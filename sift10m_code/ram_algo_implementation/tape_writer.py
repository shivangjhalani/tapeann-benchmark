#claude code optimised version with the boundary cluster resolved

import numpy as np
import json
import time
import os
import faiss
import multiprocessing
import gc
from sklearn.decomposition import PCA
from sklearn.preprocessing import MinMaxScaler
from hilbertcurve.hilbertcurve import HilbertCurve


class TapeIndexer:
    def __init__(self, dataset_path, n_clusters=10000, dim_pca=8):
        self.dataset_path  = dataset_path
        self.n_clusters    = n_clusters
        self.dim_pca       = dim_pca

        self.data_128d      = None
        self.cluster_labels = None
        self.centroids_128d = None
        self.global_mean    = None

    # ------------------------------------------------------------------
    # Phase 1: Load data and profile global mean
    # ------------------------------------------------------------------
    def load_data(self):
        print(f"[*] Loading Disjoint Base from {self.dataset_path}...")
        t0 = time.time()

        raw_data       = np.fromfile(self.dataset_path, dtype=np.float32)
        self.data_128d = raw_data.reshape(-1, 128)

        self.global_mean = np.mean(self.data_128d, axis=0).astype(np.float32)
        self.global_mean.tofile("global_mean.bin")

        print(f"[+] Loaded {self.data_128d.shape[0]:,} vectors & exported "
              f"global_mean.bin in {time.time() - t0:.2f}s")

    # ------------------------------------------------------------------
    # Phase 2: FAISS K-Means routing
    # ------------------------------------------------------------------
    def train_routing(self):
        print(f"\n[*] Training Smart Router (128D KMeans K={self.n_clusters}) using FAISS...")
        t0 = time.time()

        print("[*] Sub-sampling 1M vectors for training...")
        np.random.seed(42)
        idx    = np.random.choice(self.data_128d.shape[0], size=1_000_000, replace=False)
        subset = np.ascontiguousarray(self.data_128d[idx], dtype=np.float32)

        kmeans = faiss.Kmeans(d=128, k=self.n_clusters, niter=20,
                              verbose=True, seed=42)
        kmeans.train(subset)
        self.centroids_128d = kmeans.centroids

        print(f"[*] FAISS: Assigning all {self.data_128d.shape[0]:,} vectors to clusters...")
        _, labels           = kmeans.index.search(self.data_128d, 1)
        self.cluster_labels = labels.flatten()
        print(f"[+] Router trained & assigned in {time.time() - t0:.2f}s")

    # ------------------------------------------------------------------
    # Phase 3: Hilbert-curve spatial sort (multiprocessing)
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_hilbert_chunk(chunk):
        hc = HilbertCurve(p=16, n=8)
        return hc.distances_from_points(chunk)

    def pca_and_hilbert(self):
        print(f"\n[*] Projecting vectors to {self.dim_pca}D using PCA...")
        t0 = time.time()

        pca = PCA(n_components=self.dim_pca)
        pca.fit(self.data_128d[:1_000_000])
        data_8d = pca.transform(self.data_128d)

        domain_max    = 2**16 - 1
        scaler        = MinMaxScaler(feature_range=(0, domain_max))
        data_8d_quant = scaler.fit_transform(data_8d).astype(int)

        print("[*] Calculating Hilbert keys using Multi-Processing...")
        num_cores   = multiprocessing.cpu_count()
        print(f"    -> Distributing across {num_cores} CPU threads...")
        chunks      = np.array_split(data_8d_quant, num_cores)
        list_chunks = [c.tolist() for c in chunks]

        with multiprocessing.Pool(num_cores) as pool:
            results = pool.map(self._compute_hilbert_chunk, list_chunks)

        hilbert_keys = np.concatenate(results)

        print("[*] Sorting dataset by Cluster ID -> Hilbert Key...")
        self.sort_order    = np.lexsort((hilbert_keys, self.cluster_labels))
        self.sorted_labels = self.cluster_labels[self.sort_order]
        print(f"[+] Sorted in {time.time() - t0:.2f}s")

    # ------------------------------------------------------------------
    # Phase 4: Build the aligned binary tape
    # ------------------------------------------------------------------
    def build_tape(self, chunk_size=4096):
        print(f"\n[*] Building {chunk_size}B-Aligned Tape "
              "(Per-Dim Asymmetric Int8 + Aligned Structs)...")
        t0 = time.time()

        self.centroids_128d.astype(np.float32).tofile("centroids.bin")

        segment_table = {}
        current_offset = 0

        # Struct layout (160 bytes, matches C++ VectorRecord exactly):
        #   bitmask  : 2 × uint64  =  16 bytes @ offset 0
        #   vector   : 128 × int8  = 128 bytes @ offset 16
        #   id       : 1 × uint32  =   4 bytes @ offset 144
        #   padding  : 12 × uint8  =  12 bytes @ offset 148
        dt = np.dtype([
            ('bitmask', np.uint64, (2,)),
            ('vector',  np.int8,  (128,)),
            ('id',      np.uint32),
            ('padding', np.uint8, (12,))
        ])

        unique_clusters, start_indices, counts = np.unique(
            self.sorted_labels, return_index=True, return_counts=True)

        # Precompute bit-position powers for bitmask generation
        powers = (np.uint64(1) << np.arange(64, dtype=np.uint64))

        with open("index_tape.bin", "wb") as f:
            for i, (cls, start, count) in enumerate(
                    zip(unique_clusters, start_indices, counts)):

                cluster_sort_indices = self.sort_order[start: start + count]
                cluster_vectors      = self.data_128d[cluster_sort_indices]  # (N, 128)

                # --- Bitmask: mean-centered per vector ---
                m0 = np.sum(
                    (cluster_vectors[:, :64] > self.global_mean[:64]) * powers,
                    axis=1, dtype=np.uint64)
                m1 = np.sum(
                    (cluster_vectors[:, 64:] > self.global_mean[64:]) * powers,
                    axis=1, dtype=np.uint64)

                # ============================================================
                # FIX: Per-dimension asymmetric quantization.
                #
                # Previously: one scalar (scale, zero_point) covered all 128
                # dims. A cluster with dim0 in [0,200] and dim1 in [0,2] used
                # the same scale for both — dim1 lost almost all precision.
                #
                # Now: each of the 128 dimensions gets its own scale_d and
                # zero_point_d, mapping that dimension's full range onto
                # [-128, 127]. Exported as length-128 arrays into segment_table.
                # ============================================================
                min_per_dim  = cluster_vectors.min(axis=0)   # shape (128,)
                max_per_dim  = cluster_vectors.max(axis=0)   # shape (128,)

                # Guard against zero-range dimensions (constant feature)
                range_per_dim = max_per_dim - min_per_dim
                range_per_dim = np.where(range_per_dim == 0, 1e-9, range_per_dim)

                scale_per_dim = (range_per_dim / 255.0).astype(np.float32)

                # zero_point: the int8 value that maps to the float value 0.
                # Derived from: float_val = (int8_val - zp) * scale
                # => zp = -128 - min_per_dim / scale_per_dim
                zp_per_dim = (-128.0 - min_per_dim / scale_per_dim).astype(np.float32)

                # Quantize: int8_val = round(float_val / scale) + (-128 - min/scale)
                #                    = round(float_val / scale) + zp
                # Rearranged to the equivalent form used in the original code:
                #   round((x - min) / scale) - 128
                quantized = np.clip(
                    np.round((cluster_vectors - min_per_dim) / scale_per_dim) - 128,
                    -128, 127
                ).astype(np.int8)

                # --- Pack into the 160-byte C struct ---
                cluster_blob             = np.zeros(count, dtype=dt)
                cluster_blob['bitmask'][:, 0] = m0
                cluster_blob['bitmask'][:, 1] = m1
                cluster_blob['vector']        = quantized
                cluster_blob['id']            = cluster_sort_indices

                blob_bytes      = cluster_blob.tobytes()
                f.write(blob_bytes)
                bytes_written   = len(blob_bytes)

                padding_needed  = (chunk_size - (bytes_written % chunk_size)) % chunk_size
                f.write(b'\x00' * padding_needed)

                # ============================================================
                # Segment table entry: store per-dim arrays as JSON lists.
                # The C++ engine reads "scale_per_dim" and "zp_per_dim" as
                # float[128] arrays and uses them in the AVX2 dequantization.
                # ============================================================
                segment_table[int(cls)] = {
                    "num_vectors":   int(count),
                    "byte_offset":   int(current_offset),
                    "length_bytes":  int(bytes_written + padding_needed),
                    "scale_per_dim": scale_per_dim.tolist(),   # length 128
                    "zp_per_dim":    zp_per_dim.tolist(),      # length 128
                }

                current_offset += (bytes_written + padding_needed)

                if i % 500 == 0:
                    f.flush()
                    gc.collect()

        print(f"[+] index_tape.bin built in {time.time() - t0:.2f}s")

        print("[*] Writing segment_table.json...")
        with open("segment_table.json", "w") as f:
            json.dump(segment_table, f, separators=(',', ':'))  # compact for smaller file
        print("[+] segment_table.json written.")
        print(f"\n[*] Note: segment_table.json is now larger (~100 MB) due to per-dim arrays.")
        print(f"    Consider converting to a binary .npz format for production use.")

if __name__ == "__main__":
    dataset_path = "sift10m_base_disjoint.bin"

    indexer = TapeIndexer(dataset_path, n_clusters=10000)

    indexer.load_data()
    indexer.train_routing()
    indexer.pca_and_hilbert()
    indexer.build_tape()
#old code
'''
import numpy as np
import json
import time
import os
import faiss
import multiprocessing
import gc
from sklearn.decomposition import PCA
from sklearn.preprocessing import MinMaxScaler
from hilbertcurve.hilbertcurve import HilbertCurve

class TapeIndexer:
    def __init__(self, dataset_path, n_clusters=10000, dim_pca=8):
        self.dataset_path = dataset_path
        self.n_clusters = n_clusters
        self.dim_pca = dim_pca

        self.data_128d = None
        self.cluster_labels = None
        self.centroids_128d = None
        self.global_mean = None

    def load_data(self):
        print(f"[*] Loading Disjoint Base from {self.dataset_path}...")
        start_time = time.time()
        
        # MASSIVE SPEEDUP: Since we already extracted it from the .mat file, 
        # we just map the raw float32 binary file directly into RAM.
        raw_data = np.fromfile(self.dataset_path, dtype=np.float32)
        
        # Reshape it into the (N, 128) matrix
        self.data_128d = raw_data.reshape(-1, 128)
        
        self.global_mean = np.mean(self.data_128d, axis=0).astype(np.float32)
        self.global_mean.tofile("global_mean.bin")
        print(f"[+] Loaded {self.data_128d.shape[0]} vectors & exported global_mean.bin in {time.time() - start_time:.2f}s")

    def train_routing(self):
        print(f"\n[*] Training Smart Router (128D KMeans K={self.n_clusters}) using FAISS...")
        start_time = time.time()
        
        print("[*] Sub-sampling 1M vectors for training...")
        np.random.seed(42)
        subset_indices = np.random.choice(self.data_128d.shape[0], size=1000000, replace=False)
        train_subset = np.ascontiguousarray(self.data_128d[subset_indices], dtype=np.float32)
        
        kmeans = faiss.Kmeans(d=128, k=self.n_clusters, niter=20, verbose=True, seed=42)
        kmeans.train(train_subset) 
        self.centroids_128d = kmeans.centroids
        
        print(f"[*] FAISS: Assigning all {self.data_128d.shape[0]} vectors to clusters...")
        _, labels = kmeans.index.search(self.data_128d, 1)
        self.cluster_labels = labels.flatten()
        print(f"[+] Router trained & vectors assigned in {time.time() - start_time:.2f}s")

    @staticmethod
    def _compute_hilbert_chunk(chunk):
        hc = HilbertCurve(p=16, n=8)
        return hc.distances_from_points(chunk)

    def pca_and_hilbert(self):
        print(f"\n[*] Projecting vectors to {self.dim_pca}D using PCA...")
        start_time = time.time()
        
        pca = PCA(n_components=self.dim_pca)
        subset_for_pca = self.data_128d[:1000000] 
        pca.fit(subset_for_pca)
        data_8d = pca.transform(self.data_128d)

        p = 16 
        domain_max = 2**p - 1
        scaler = MinMaxScaler(feature_range=(0, domain_max))
        data_8d_quant = scaler.fit_transform(data_8d).astype(int)

        print(f"[*] Calculating Hilbert keys using Multi-Processing...")
        num_cores = multiprocessing.cpu_count()
        print(f"    -> Distributing across {num_cores} CPU threads...")
        
        chunks = np.array_split(data_8d_quant, num_cores)
        list_chunks = [chunk.tolist() for chunk in chunks]
        
        with multiprocessing.Pool(num_cores) as pool:
            results = pool.map(self._compute_hilbert_chunk, list_chunks)
            
        hilbert_keys = np.concatenate(results)
        
        print("[*] Sorting dataset by Cluster ID -> Hilbert Key...")
        self.sort_order = np.lexsort((hilbert_keys, self.cluster_labels))
        self.sorted_labels = self.cluster_labels[self.sort_order]
        print(f"[+] Data sorted in {time.time() - start_time:.2f}s")

    def build_tape(self, chunk_size=4096):
        print(f"\n[*] Building {chunk_size}B-Aligned Tape (Asymmetric Int8 + Aligned Structs)...")
        start_time = time.time()

        self.centroids_128d.astype(np.float32).tofile("centroids.bin")
        
        segment_table = {}
        current_offset = 0

        dt = np.dtype([
            ('bitmask', np.uint64, (2,)), 
            ('vector', np.int8, (128,)), 
            ('id', np.uint32),
            ('padding', np.uint8, (12,))
        ])
        
        unique_clusters, start_indices, counts = np.unique(self.sorted_labels, return_index=True, return_counts=True)
        powers = (np.uint64(1) << np.arange(64, dtype=np.uint64))

        with open("index_tape.bin", "wb") as f:
            for i, (cls, start, count) in enumerate(zip(unique_clusters, start_indices, counts)):
                
                cluster_sort_indices = self.sort_order[start : start + count]
                cluster_vectors = self.data_128d[cluster_sort_indices]
                
                m0 = np.sum((cluster_vectors[:, :64] > self.global_mean[:64]) * powers, axis=1, dtype=np.uint64)
                m1 = np.sum((cluster_vectors[:, 64:] > self.global_mean[64:]) * powers, axis=1, dtype=np.uint64)

                min_val = np.min(cluster_vectors)
                max_val = np.max(cluster_vectors)
                if max_val == min_val: max_val = min_val + 1e-9
                scale = (max_val - min_val) / 255.0
                zero_point = -128.0 - (min_val / scale)
                
                quantized_vectors = np.clip(np.round((cluster_vectors - min_val) / scale) -128,-128, 127).astype(np.int8)

                cluster_blob = np.zeros(count, dtype=dt)
                cluster_blob['bitmask'][:, 0] = m0
                cluster_blob['bitmask'][:, 1] = m1
                cluster_blob['vector'] = quantized_vectors
                
                # The ID is exactly the original row index, which preserves Ground Truth mapping
                cluster_blob['id'] = cluster_sort_indices 
                
                blob_bytes = cluster_blob.tobytes()
                f.write(blob_bytes)
                bytes_written = len(blob_bytes)
                
                padding_needed = (chunk_size - (bytes_written % chunk_size)) % chunk_size
                f.write(b'\x00' * padding_needed)
                
                segment_table[int(cls)] = {
                    "num_vectors": int(count),
                    "byte_offset": int(current_offset),
                    "length_bytes": int(bytes_written + padding_needed),
                    "scale": float(scale),
                    "zero_point": float(zero_point)
                }
                
                current_offset += (bytes_written + padding_needed)

                if i % 500 == 0:
                    f.flush()
                    gc.collect()
                
        print(f"[+] index_tape.bin built in {time.time() - start_time:.2f}s")
        with open("segment_table.json", "w") as f:
            json.dump(segment_table, f, indent=4)

if __name__ == "__main__":
    # POINT TO THE NEW DISJOINT BASE FILE
    dataset_path = "sift10m_base_disjoint.bin"
    
    indexer = TapeIndexer(dataset_path, n_clusters=10000)
    indexer.load_data()
    indexer.train_routing()
    indexer.pca_and_hilbert()
    indexer.build_tape()


'''