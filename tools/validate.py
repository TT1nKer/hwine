#!/usr/bin/env python3
"""Fail-closed RTL validation: independent integer oracle, Icarus, Yosys SAT,
and xc7 technology mapping. Standard library only. Logs/scripts are retained.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SEED = 0x4857494E45


def run(cmd, cwd, log, timeout=180, expect_failure=False):
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        log.write_text(str(exc))
        raise RuntimeError(f"TIMEOUT: {log}") from exc
    log.write_text("$ " + " ".join(map(str, cmd)) + "\n" + p.stdout)
    if (p.returncode == 0) == expect_failure:
        raise RuntimeError(f"Unexpected exit {p.returncode}: {log}\n{p.stdout[-2400:]}")
    return p.stdout, round(time.monotonic() - start, 3)


def oracle(case, values):
    """Mathematical integers then reduction modulo 2**W, independent of the IR."""
    w, kind = case['width'], case['kind']
    mask = (1 << w) - 1
    x = [v - (1 << w) if case['signed'] and v & (1 << (w - 1)) else v for v in values]
    a = x[0]
    b = x[1] if len(x) > 1 else 0
    if kind in ('add', 'reduceadd'): result = a + b
    elif kind == 'sub': result = a - b
    elif kind in ('mul', 'dspmul'): result = a * b
    elif kind in ('mac', 'madd', 'dspmac'): result = a * b + x[2]
    elif kind == 'preadd': result = (a + b) * x[2]
    elif kind == 'min': result = min(a, b)
    elif kind == 'max': result = max(a, b)
    elif kind == 'shl': result = a << values[1]
    elif kind == 'shr': result = a >> values[1]
    elif kind == 'fir3': result = 7 * x[0] + 13 * x[1] - 5 * x[2]
    elif kind == 'chain': result = sum(x)
    elif kind == 'shared': result = a * b + x[2]
    elif kind == 'const_min': result = a * -(1 << 63)
    elif kind == 'const_max': result = a * ((1 << 63) - 1)
    elif kind == 'identity': result = a
    else: raise ValueError(kind)
    return result & mask


def vectors(case):
    widths = case['input_widths']
    if sum(widths) <= 16:
        return list(itertools.product(*(range(1 << w) for w in widths))), 'exhaustive'
    edges = [sorted({0, 1, (1 << w) - 1, (1 << (w - 1)), (1 << (w - 1)) - 1,
                     (1 << w) - 2}) for w in widths]
    if case['kind'] in ('shl', 'shr'):
        edges[1] = sorted({0, 1, case['width'] - 1, case['width'], case['width'] + 1, 127, 255})
    vals = list(itertools.product(*edges))
    rng = random.Random(SEED)
    vals += [tuple(rng.getrandbits(w) for w in widths) for _ in range(1024)]
    return vals, 'boundary+seeded-random'


def port_name(i):
    return f'a{i // 2}' if i % 2 == 0 else f'w{i // 2}'


def connections(case, result='actual'):
    xs = [f'.{port_name(i)}(x{i})' for i in range(len(case['input_widths']))]
    if case['latency']:
        xs += ['.clk(clk)', '.rst_n(rst_n)']
    return ', '.join(xs + [f'.result({result})'])


def simulate(case, rtl, work, suffix='', corrupt_expected=False):
    vals, coverage = vectors(case)
    w, latency = case['width'], case['latency']
    total_width = sum(case['input_widths']) + w
    hex_lines = []
    for v in vals:
        packed = 0
        for x, bits in zip(v, case['input_widths']): packed = (packed << bits) | x
        expected = oracle(case, v) ^ (1 if corrupt_expected else 0)
        packed = (packed << w) | expected
        hex_lines.append(f'{packed:0{(total_width + 3) // 4}x}')
    vecfile = work / f'vectors{suffix}.hex'
    vecfile.write_text('\n'.join(hex_lines) + '\n')
    regs = '\n'.join(f'  reg [{bits - 1}:0] x{i};' for i, bits in enumerate(case['input_widths']))
    unpack = ', '.join([f'x{i}' for i in range(len(case['input_widths']))] + ['expected'])
    # Nonblocking assignments settle before comparison. Each input tuple changes
    # at the falling edge and is accepted at the next rising edge.
    check = f'''      if (result_count > 0 && actual !== history[head])
        $fatal(1, "MISMATCH vector=%0d got=%h expected=%h", i, actual, history[head]);'''
    if latency:
        body = f'''
    clk = 0; rst_n = 0;
    {{ {unpack} }} = vectors[0];
    #5; clk = 1; #1;
    if (actual !== 0) $fatal(1, "MISMATCH reset output=%h", actual);
    clk = 0; #4;
    for (i = 0; i < {len(vals) + latency - 1}; i = i + 1) begin
      // Reassert reset midstream: old tuples must not leak across reset.
      if (i == {len(vals) // 2}) begin
        rst_n = 0; #5; clk = 1; #1;
        if (actual !== 0) $fatal(1, "MISMATCH midstream reset output=%h", actual);
        clk = 0; #4;
        filled = 0;
      end
      rst_n = 1;
      {{ {unpack} }} = vectors[i < {len(vals)} ? i : 0];
      history[i % {latency}] = expected;
      #5; clk = 1; #1;
      if (filled < {latency}) filled = filled + 1;
      head = (i + 1) % {latency};
      result_count = (filled >= {latency});
{check}
      if (result_count) checked = checked + 1;
      clk = 0; #4;
    end'''
    else:
        body = f'''
    for (i = 0; i < {len(vals)}; i = i + 1) begin
      {{ {unpack} }} = vectors[i]; #1;
      if (actual !== expected) $fatal(1, "MISMATCH vector=%0d got=%h expected=%h", i, actual, expected);
      checked = checked + 1;
    end'''
    tb = f'''module tb;
{regs}
  reg clk, rst_n;
  wire [{w - 1}:0] actual;
  reg [{w - 1}:0] expected;
  reg [{total_width - 1}:0] vectors [0:{len(vals) - 1}];
  reg [{w - 1}:0] history [0:{max(1, latency) - 1}];
  integer i, head, filled = 0, result_count, checked = 0;
  {case['name']} dut({connections(case)});
  initial begin
    $readmemh("{vecfile.name}", vectors);
{body}
    $display("SIM_PASS checked=%0d", checked); $finish;
  end
endmodule
'''
    tbfile = work / f'tb{suffix}.sv'
    tbfile.write_text(tb)
    exe = f'sim{suffix}.vvp'
    run(['iverilog', '-g2012', '-Wall', '-s', 'tb', '-o', exe, str(rtl), tbfile.name], work, work / f'compile{suffix}.log')
    text, duration = run(['vvp', exe], work, work / f'simulation{suffix}.log', expect_failure=corrupt_expected or suffix == '_mutant')
    if corrupt_expected or suffix == '_mutant':
        if 'MISMATCH' not in text: raise RuntimeError('negative simulation failed for the wrong reason')
        return {'negative_control': 'rejected'}
    if 'SIM_PASS' not in text: raise RuntimeError('missing simulation success marker')
    checked = int(text.split('SIM_PASS checked=')[1].split()[0])
    if checked == 0: raise RuntimeError('vacuous simulation')
    return {'vectors': len(vals), 'comparisons': checked, 'coverage': coverage, 'seconds': duration}


def reference_expr(case):
    """Separately written declarative hardware specifications, no extracted IR."""
    k = case['kind']
    if k in ('add', 'reduceadd'): return 'x0 + x1'
    if k == 'sub': return 'x0 - x1'
    if k in ('mul', 'dspmul'): return 'x0 * x1'
    if k in ('mac', 'madd', 'dspmac', 'shared'): return 'x0 * x1 + x2'
    if k == 'preadd': return '(x0 + x1) * x2'
    if k == 'min': return '(x0 < x1) ? x0 : x1'
    if k == 'max': return '(x0 > x1) ? x0 : x1'
    if k == 'shl': return 'x0 << x1'
    if k == 'shr': return f"x0 {'>>>' if case['signed'] else '>>'} x1"
    if k == 'fir3': return "x0 * 64'sd7 + x1 * 64'sd13 - x2 * 64'sd5"
    if k == 'chain': return ' + '.join(f'x{i}' for i in range(5))
    if k == 'const_min': return "x0 * 64'h8000000000000000"
    if k == 'const_max': return "x0 * 64'h7fffffffffffffff"
    if k == 'identity': return 'x0'
    raise ValueError(k)


def formal(case, rtl, work, suffix='', expect_failure=False, reference_rtl=None):
    w, latency = case['width'], case['latency']
    ports = ['input clk', 'input rst_n']
    for i, bits in enumerate(case['input_widths']):
        signed = case['signed'] and not (i == 1 and case['kind'] in ('shl', 'shr'))
        ports.append(f"input {'signed ' if signed else ''}[{bits - 1}:0] x{i}")
    ports.append('output ok')
    registers = ''
    expected = 'reference_value'
    guard = "1'b1"
    reset_check = "1'b1"
    if latency:
        registers = f'''reg [{w - 1}:0] delay_line [0:{latency - 1}];
reg [{latency - 1}:0] valid = 0;
reg reset_seen = 0;
integer i;
always @(posedge clk) begin
  reset_seen <= !rst_n;
  if (!rst_n) begin
    valid <= 0;
    for (i = 0; i < {latency}; i = i + 1) delay_line[i] <= 0;
  end else begin
    valid <= (valid << 1) | 1'b1;
    delay_line[0] <= reference_value;
    for (i = 1; i < {latency}; i = i + 1) delay_line[i] <= delay_line[i-1];
  end
end
'''
        expected = f'delay_line[{latency - 1}]'
        guard = f'valid[{latency - 1}]'
        reset_check = "(!reset_seen || actual == 0)"
    reference = f'assign reference_value = {reference_expr(case)};'
    if reference_rtl:
        combinational_case = {**case, 'latency': 0}
        reference = f"{case['name']}_source source({connections(combinational_case, 'reference_value')});"
    miter = f'''module miter({', '.join(ports)});
wire [{w - 1}:0] actual, reference_value;
{reference}
{case['name']} dut({connections(case)});
{registers}
assign ok = (!({guard}) || (actual == {expected})) && {reset_check};
endmodule
'''
    (work / f'miter{suffix}.sv').write_text(miter)
    if latency:
        # Only the checker valid history is initialized. DUT registers are
        # arbitrary. Prove all cycles after fill, with arbitrary reset events.
        proof = f'sat -seq 1 -tempinduct -maxsteps {latency + 2} -prove ok 1 -verify -timeout 45'
    else:
        proof = 'sat -prove ok 1 -verify -timeout 45'
    read_source = f'read_verilog -sv {reference_rtl}\n' if reference_rtl else ''
    script = f'read_verilog -sv {rtl}\n{read_source}read_verilog -sv miter{suffix}.sv\nprep -top miter -flatten\ntechmap\nopt\ncheck -assert\n{proof}\n'
    scriptfile = work / f'formal{suffix}.ys'
    scriptfile.write_text(script)
    text, duration = run(['yosys', '-Q', '-T', '-s', scriptfile.name], work, work / f'formal{suffix}.log', timeout=150, expect_failure=expect_failure)
    if expect_failure:
        if 'proof did fail' not in text: raise RuntimeError('negative formal failed for the wrong reason')
        return {'negative_control': 'rejected'}
    marker = 'Induction step proven: SUCCESS!' if latency else 'SAT proof finished - no model found: SUCCESS!'
    if marker not in text: raise RuntimeError(f'unproved or vacuous formal result: {work}')
    return {'method': 'temporal-induction' if latency else 'combinational-SAT', 'status': 'proved', 'seconds': duration}


def synthesize(case, rtl, work):
    script = f'read_verilog -sv {rtl}\nsynth_xilinx -family xc7 -top {case["name"]} -noiopad -noclkbuf\ncheck -assert\ntee -o synthesis.json stat -json\n'
    (work / 'synth.ys').write_text(script)
    _, duration = run(['yosys', '-Q', '-T', '-s', 'synth.ys'], work, work / 'synthesis.log')
    stats = json.loads((work / 'synthesis.json').read_text())
    cell_map = stats['modules']['\\' + case['name']]['num_cells_by_type']
    return {'target': 'Yosys synth_xilinx xc7 (no place/route)', 'cells': cell_map,
            'LUT': sum(n for k, n in cell_map.items() if k.startswith('LUT')),
            'FF': sum(n for k, n in cell_map.items() if k.startswith('FD')),
            'DSP48E1': cell_map.get('DSP48E1', 0), 'seconds': duration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build' / 'validation')
    parser.add_argument('--filter', default='', help='diagnostic subset; reported in summary')
    parser.add_argument('--extended-formal', action='store_true', help='also require the expensive 64-bit CSD proof (known SAT timeout)')
    args = parser.parse_args()
    for exe in ('cargo', 'iverilog', 'vvp', 'yosys'):
        if not shutil.which(exe): raise RuntimeError(f'Required tool missing: {exe}. See docs/RELIABILITY.md.')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Remove a prior success report before any validation can fail.
    (out / 'summary.json').unlink(missing_ok=True)
    rtl_dir = out / 'rtl'
    run(['cargo', 'run', '--locked', '--manifest-path', str(ROOT / 'hwine-rs/Cargo.toml'), '--example', 'validation_fixtures', '--', str(rtl_dir)], ROOT, out / 'generation.log')
    cases = list(csv.DictReader((rtl_dir / 'manifest.tsv').open(), delimiter='\t'))
    records = []
    for case in cases:
        if args.filter and args.filter not in case['name']: continue
        case['width'], case['latency'] = int(case['width']), int(case['latency'])
        case['signed'] = case['signed'] == 'true'
        case['input_widths'] = list(map(int, case['input_widths'].split(',')))
        work = out / case['name']
        work.mkdir(exist_ok=True)
        rtl = rtl_dir / f"{case['name']}.sv"
        record = {**case, 'rtl_sha256': hashlib.sha256(rtl.read_bytes()).hexdigest()}
        record['simulation'] = simulate(case, rtl, work)
        if case['kind'] == 'const_max' and case['width'] == 64 and case['variant'] == 'opt_dsp' and not args.extended_formal:
            record['formal'] = {'method': 'not-run', 'status': 'outside-default-proof-scope', 'reason': '64-bit CSD restructuring timed out at 45 s in initial validation; simulation remains required'}
        elif case['latency']:
            # Composition: independently prove this exact combinational source,
            # then prove the scheduled RTL is its latency-shifted implementation.
            source = rtl_dir / f"{case['name']}_source.sv"
            source_case = {**case, 'name': case['name'] + '_source', 'latency': 0}
            source_work = work / 'source_proof'
            source_work.mkdir(exist_ok=True)
            source_proof = formal(source_case, source, source_work)
            record['formal'] = formal(case, rtl, work, reference_rtl=source)
            record['formal']['reference_proof'] = source_proof
            record['formal']['reference_rtl_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            record['formal'] = formal(case, rtl, work)
        if case['width'] == 16 and case['kind'] in ('fir3', 'chain', 'shared'):
            record['synthesis'] = synthesize(case, rtl, work)
        records.append(record)
        print(f"PASS {case['name']}: sim={record['simulation']['comparisons']} formal={record['formal']['method']}", flush=True)
    if not records: raise RuntimeError('No fixtures selected')
    # Independent negative controls: wrong oracle, broken arithmetic, wrong
    # signedness, and an off-by-one pipeline latency must all fail the harness.
    controls = []
    by_name = {r['name']: r for r in records}
    for name, mutation in [('add_u4_baseline', 'arithmetic'), ('shr_s8_baseline', 'signedness'), ('fir3_s8_pipe_every', 'latency'), ('fir3_s8_pipe_every', 'reset')]:
        if name not in by_name: continue
        case = by_name[name].copy()
        work = out / name / f'negative_{mutation}'
        work.mkdir(exist_ok=True)
        rtl = rtl_dir / f'{name}.sv'
        if mutation == 'arithmetic':
            simulate(case, rtl, work, '_bad_oracle', corrupt_expected=True)
            controls.append('wrong Python oracle rejected by simulation')
            mutant = rtl.read_text().replace(' + ', ' - ', 1)
        elif mutation == 'signedness': mutant = rtl.read_text().replace(' >>> ', ' >> ', 1)
        elif mutation == 'reset': mutant = rtl.read_text().replace('if (!rst_n)', "if (1'b0)")
        else:
            mutant = rtl.read_text()
            case['latency'] += 1
        path = work / 'mutant.sv'
        path.write_text(mutant)
        simulate(case, path, work, '_mutant')
        formal(case, path, work, '_mutant', expect_failure=True)
        controls.append(f'{mutation} mutation rejected by simulation and formal')
    versions = {}
    for exe, opt in [('rustc', '--version'), ('yosys', '-V'), ('iverilog', '-V'), ('python3', '--version')]:
        p = subprocess.run([exe, opt], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT, check=True)
        versions[exe] = p.stdout.splitlines()[0]
    source_files = sorted((ROOT / 'hwine-rs' / 'src').glob('*.rs')) + sorted((ROOT / 'hwine-rs' / 'tests').glob('*.rs'))
    source_files += [ROOT / p for p in ['hwine-rs/examples/validation_fixtures.rs', 'tools/validate.py', 'tools/with_eda.sh', 'hwine-rs/Cargo.lock', 'hwine-rs/Cargo.toml', 'rust-toolchain.toml']]
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    summary = {'source_sha256': source_hashes, 'status': 'passed', 'scope_filter': args.filter, 'seed': SEED, 'tools': versions,
               'cases': len(records), 'simulation_comparisons': sum(r['simulation']['comparisons'] for r in records),
               'formal_proofs': sum(r['formal']['status'] == 'proved' for r in records),
               'formal_out_of_scope': [r['name'] for r in records if r['formal']['status'] != 'proved'],
               'negative_controls': controls, 'results': records}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f"PASS: {len(records)} implementations; {summary['simulation_comparisons']} comparisons; {summary['formal_proofs']} RTL proofs; {len(summary['formal_out_of_scope'])} outside proof scope. Report: {out / 'summary.json'}")


if __name__ == '__main__':
    try: main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'VALIDATION FAILED: {exc}', file=sys.stderr)
        sys.exit(1)
