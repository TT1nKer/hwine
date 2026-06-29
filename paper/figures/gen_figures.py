import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import csv

STYLE = {
    'font.family': 'serif',
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.labelsize': 10,
    'legend.fontsize': 9,
}

# ====== Figure 1: Adder tree Fmax scaling ======
data = []
with open('/Users/hostsjim/project/hwine/paper/data/adder_fmax.csv') as f:
    for row in csv.DictReader(f):
        data.append({k: int(v) if k=='n' else float(v) for k,v in row.items()})

ns = [d['n'] for d in data]
serial = [d['serial_fmax_mhz'] for d in data]
pipe = [d['pipe_fmax_mhz'] for d in data]

plt.rcParams.update(STYLE)
fig, ax = plt.subplots(figsize=(5, 3.2))
ax.plot(ns, serial, 's-', label='Serial (combinational)', color='#d62728', linewidth=1.5, markersize=6)
ax.plot(ns, pipe, 'o-', label='Pipelined (fine-grained)', color='#2ca02c', linewidth=1.5, markersize=6)
ax.axhline(y=226, color='gray', linestyle='--', alpha=0.5, label='226 MHz (constant)')
ax.set_xlabel('Taps')
ax.set_ylabel('Fmax (MHz)')
ax.set_title('Pure Adder Tree: Fmax vs Scale')
ax.legend(loc='lower left')
ax.set_xlim(10, 170)
ax.set_ylim(50, 280)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig('/Users/hostsjim/project/hwine/paper/figures/fig1_adder_fmax.pdf', dpi=300)
plt.close()

# ====== Figure 2: Runtime scaling ======
data = []
with open('/Users/hostsjim/project/hwine/paper/data/scaling.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        data.append({k: float(v) for k,v in row.items()})

ns2 = [int(d['n']) for d in data]
times = [d['time_ms'] for d in data]
classes = [d['classes'] for d in data]
iters = [d['iters'] for d in data]

fig, ax1 = plt.subplots(figsize=(5, 3.2))
ax2 = ax1.twinx()
bars = ax1.bar([f'{n}' for n in ns2], times, color='#1f77b4', alpha=0.7, label='Time (ms)')
ax2.plot([f'{n}' for n in ns2], classes, 'D-', color='#ff7f0e', linewidth=1.5, markersize=5, label='E-classes')
ax1.set_xlabel('Input Size N')
ax1.set_ylabel('Saturation Time (ms)', color='#1f77b4')
ax2.set_ylabel('E-classes', color='#ff7f0e')
ax1.set_title('E-Graph Runtime Scaling')
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
ax1.grid(True, alpha=0.3, axis='y')
fig.tight_layout()
fig.savefig('/Users/hostsjim/project/hwine/paper/figures/fig2_runtime.pdf', dpi=300)
plt.close()

# ====== Figure 3: hwine vs Kastner FIR6 ======
categories = ['LUT', 'FF', 'CARRY4', 'Fmax']
hwine_vals = [154, 463, 40, 306]
kastner_vals = [246, 449, 60, 308]
x = np.arange(len(categories))
width = 0.35

fig, ax = plt.subplots(figsize=(5, 3.2))
bars1 = ax.bar(x - width/2, hwine_vals, width, label='hwine (auto)', color='#2ca02c', alpha=0.85)
bars2 = ax.bar(x + width/2, kastner_vals, width, label='Kastner (expert)', color='#d62728', alpha=0.85)

# Annotate ratios
ratios = ['0.63×', '1.03×', '0.67×', '99.3%']
for i, (bar, ratio) in enumerate(zip(bars1, ratios)):
    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 5, ratio,
            ha='center', va='bottom', fontsize=8, fontweight='bold')

ax.set_xticks(x)
ax.set_xticklabels(categories)
ax.set_title('hwine vs Kastner Hand-Optimized FIR6')
ax.legend(loc='upper right')
ax.grid(True, alpha=0.3, axis='y')
ax.set_ylabel('Count / MHz')
fig.tight_layout()
fig.savefig('/Users/hostsjim/project/hwine/paper/figures/fig3_kastner_compare.pdf', dpi=300)
plt.close()

# ====== Figure 4: DSP FIR Fmax scaling ======
data = []
with open('/Users/hostsjim/project/hwine/paper/data/dsp_fir_fmax.csv') as f:
    for row in csv.DictReader(f):
        data.append({k: float(v) for k,v in row.items()})

ns4 = [int(d['n']) for d in data]
ser4 = [d['serial_fmax_mhz'] for d in data]
pipe4 = [d['pipe_fmax_mhz'] for d in data]

fig, ax = plt.subplots(figsize=(5, 3.2))
ax.plot(ns4, ser4, 's-', label='Serial DSP cascade', color='#d62728', linewidth=1.5, markersize=6)
ax.plot(ns4, pipe4, 'o-', label='Pipelined DSP', color='#2ca02c', linewidth=1.5, markersize=6)
ax.set_xlabel('Taps')
ax.set_ylabel('Fmax (MHz)')
ax.set_title('Full FIR (DSP48E1): Fmax vs Scale')
ax.legend()
ax.set_xlim(4, 45)
ax.set_ylim(0, 370)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig('/Users/hostsjim/project/hwine/paper/figures/fig4_dsp_fir.pdf', dpi=300)
plt.close()

print("All 4 figures generated:")
import os
for f in sorted(os.listdir('/Users/hostsjim/project/hwine/paper/figures')):
    if f.endswith('.pdf'):
        sz = os.path.getsize(os.path.join('/Users/hostsjim/project/hwine/paper/figures', f))
        print(f"  {f} ({sz//1024}KB)")
