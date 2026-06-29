import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv

data = []
with open('/Users/hostsjim/project/hwine/paper/data/hwine_vs_kastner_all.csv') as f:
    for row in csv.DictReader(f):
        data.append({k: int(v) if k != 'kastner_var' else v for k,v in row.items()})

ns = [d['n'] for d in data]
hwine = [d['hwine_lut'] for d in data]
kastner = [d['kastner_lut'] for d in data]

fig, ax = plt.subplots(figsize=(7, 3.5))
x = range(len(ns))
width = 0.35
bars1 = ax.bar([i - width/2 for i in x], hwine, width, label='hwine (auto)', color='#2ca02c', alpha=0.85)
bars2 = ax.bar([i + width/2 for i in x], kastner, width, label='Kastner (expert)', color='#d62728', alpha=0.85)

# Annotate ratios
for i, (h, k) in enumerate(zip(hwine, kastner)):
    ratio = h / k
    ax.text(i, max(h, k) + 100, f'{ratio:.2f}×', ha='center', fontsize=7, fontweight='bold',
            color='green' if ratio < 1 else 'red')

ax.set_xticks(x)
ax.set_xticklabels([str(n) for n in ns])
ax.set_xlabel('Taps')
ax.set_ylabel('Slice LUTs')
ax.set_title('hwine vs Kastner FIR: LUT Count by Tap Count\n(Fmax = 308 MHz for all designs)')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')
fig.tight_layout()
fig.savefig('/Users/hostsjim/project/hwine/paper/figures/fig5_hwine_vs_kastner.pdf', dpi=300)
plt.close()
print("Figure 5 generated")
