import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# Data from TapeANN Bare Metal Benchmarks (SIFT10M)
# ==========================================
probes = [20, 40, 60, 80, 100]
latencies = [1.67012, 2.70298, 4.0394, 5.09693, 6.46734]
recalls = [85.112, 92.011, 94.635, 95.953, 96.655]

# Calculate Queries Per Second (QPS) for 1 thread
# QPS = 1000 ms / Average Latency in ms
qps = [1000.0 / lat for lat in latencies]

# ==========================================
# Graph Styling (Academic / Paper Style)
# ==========================================
sns.set_theme(style="whitegrid")
plt.rcParams.update({
    'font.size': 12,
    'axes.labelsize': 14,
    'axes.titlesize': 16,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 12,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
fig.suptitle("TapeANN: Bare-Metal SSD Search Performance (SIFT10M SCALE)", fontweight='bold', fontsize=18)

# ------------------------------------------
# Plot 1: Recall vs Latency
# ------------------------------------------
ax1.plot(recalls, latencies, marker='o', markersize=8, linewidth=2, color='#d62728', label="TapeANN (io_uring)")
ax1.set_title("Search Latency vs. Recall@10")
ax1.set_xlabel("Recall@10 (%)")
ax1.set_ylabel("Average Latency (ms)")
ax1.set_xlim(80, 100)
ax1.set_ylim(0, 8)

# Annotate the number of probes on the graph
for i, txt in enumerate(probes):
    ax1.annotate(f"{txt} probes", (recalls[i], latencies[i]), 
                 textcoords="offset points", xytext=(-10, 10), ha='center', fontsize=10)

ax1.legend(loc="lower right")

# ------------------------------------------
# Plot 2: Recall vs Throughput (QPS)
# ------------------------------------------
ax2.plot(recalls, qps, marker='s', markersize=8, linewidth=2, color='#1f77b4', label="TapeANN (io_uring)")
ax2.set_title("Throughput (QPS) vs. Recall@10")
ax2.set_xlabel("Recall@10 (%)")
ax2.set_ylabel("Queries Per Second (QPS)")
ax2.set_xlim(70, 100)
ax2.set_ylim(0, 1000)

# Annotate the number of probes on the graph
for i, txt in enumerate(probes):
    ax2.annotate(f"{txt} probes", (recalls[i], qps[i]), 
                 textcoords="offset points", xytext=(-10, 10), ha='center', fontsize=10)

ax2.legend(loc="lower left")

# ==========================================
# Save and Show
# ==========================================
plt.tight_layout()
plt.subplots_adjust(top=0.88) # Adjust title spacing
plt.savefig("tapeann_pareto_frontier.png", dpi=300)
print("[+] Graph saved successfully as 'tapeann_pareto_frontier.png'")
plt.show()