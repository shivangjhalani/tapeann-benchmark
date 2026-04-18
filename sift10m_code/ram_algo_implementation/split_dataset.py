import h5py
import numpy as np
import time
import os

dataset_dir = os.path.join(os.path.dirname(__file__), "../sift10m_dataset/SIFT10M")
MAT_PATH = os.path.join(dataset_dir, "SIFT10Mfeatures.mat")
N_QUERIES = 10000

print("[*] Loading SIFT10M .mat file...")
start_time = time.time()
with h5py.File(MAT_PATH, 'r') as f:
    key = list(f.keys())[0]
    data = f[key]
    if data.shape[0] == 128:
        all_data = np.array(data).T
    else:
        all_data = np.array(data)

print(f"[+] Loaded {all_data.shape[0]} vectors in {time.time() - start_time:.2f}s")

# --- STRICT DISJOINT SPLIT ---
base_only = all_data[:-N_QUERIES] 
queries_only = all_data[-N_QUERIES:] 

print(f"[*] Base dimensions: {base_only.shape}")
print(f"[*] Query dimensions: {queries_only.shape}")

print("[*] Exporting disjoint base file (this might take a minute)...")
np.ascontiguousarray(base_only, dtype=np.float32).tofile("sift10m_base_disjoint.bin")

print("[*] Exporting disjoint queries...")
np.ascontiguousarray(queries_only, dtype=np.float32).tofile("test_queries_disjoint.bin")

print("[+] Split complete. You now have perfect academic disjoint sets!")
