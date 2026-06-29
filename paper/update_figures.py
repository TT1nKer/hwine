# Patch main.typ to replace ASCII tables with figure references where appropriate
# Then compile
import re

with open('main.typ', 'r') as f:
    content = f.read()

# Add figure includes after the Evaluation section header
# Insert fig1 after Experiment 1
old = "#heading(level: 2)[A. Experiment 1: Pure Adder Tree Scaling]\n\nWe evaluate pure addition trees"
new = "#heading(level: 2)[A. Experiment 1: Pure Adder Tree Scaling]\n\n#figure(image(\"figures/fig1_adder_fmax.pdf\", width: 100%), caption: [Pure adder tree: Vivado synthesis results showing pipelined Fmax constant at 226 MHz.])\n\nWe evaluate pure addition trees"
content = content.replace(old, new)

# After Experiment 5, add runtime figure
old = "#heading(level: 2)[E. Experiment 5: Runtime Scaling]\n\n#figure(\n  table("
new = "#heading(level: 2)[E. Experiment 5: Runtime Scaling]\n\n#figure(image(\"figures/fig2_runtime.pdf\", width: 100%), caption: [E-graph saturation runtime scaling. N=512 saturates in 10 ms.])\n\n#figure(\n  table("
content = content.replace(old, new)

# Add Kastner comparison figure
old = "#heading(level: 2)[C. Experiment 3: Const-Folded Shift-Add FIR vs. Kastner Benchmarks]"
new = "#heading(level: 2)[C. Experiment 3: Const-Folded Shift-Add FIR vs. Kastner Benchmarks]\n\n#figure(image(\"figures/fig3_kastner_compare.pdf\", width: 100%), caption: [hwine vs. Kastner hand-optimized 6-tap FIR. hwine matches Fmax within 0.7% with fewer resources.])"
content = content.replace(old, new)

with open('main.typ', 'w') as f:
    f.write(content)

print("main.typ updated with figure references")
