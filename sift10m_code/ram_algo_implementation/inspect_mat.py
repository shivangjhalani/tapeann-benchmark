import h5py
import os

dataset_path = "/home/grass/Documents/capstone/tapeANN_code/sift10m_code/sift10m_dataset/SIFT10M/SIFT10Mfeatures.mat"

with h5py.File(dataset_path, 'r') as f:
    print("Keys in MAT file:")
    for k in f.keys():
        if not k.startswith('#'):
            print(f"- {k}: {f[k].shape}, {f[k].dtype}")
