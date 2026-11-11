#!/usr/bin/env python3
"""Verified, measured ECP5 design-space pilot (stdlib only).

All candidates have signed wrapping arithmetic, II=1, synchronous active-low
reset, and a declared latency (default 4) including an input register. This is an arithmetic
kernel experiment, not a streaming FIR implementation or a board Fmax test.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import threading
import time
import linear_check

ROOT = Path(__file__).resolve().parents[1]
SEED = 0x4857494E45
LOCKS = {}
LOCK_GUARD = threading.Lock()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(value).hexdigest()


def dump(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def run(cmd, work, log, timeout=120):
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=work, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        output, code = p.stdout, p.returncode
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes):
            output = output.decode(errors='replace')
        output += '\nEXTERNAL_TIMEOUT\n'
        code = 124
    (work / log).write_text('$ ' + ' '.join(map(str, cmd)) + '\n' + output)
    return output, code, round(time.monotonic() - start, 3)


def checked(cmd, work, log, timeout=120):
    output, code, seconds = run(cmd, work, log, timeout)
    if code:
        raise RuntimeError(f'{work / log}: exit {code}\n{output[-1800:]}')
    return output, seconds


def port(i):
    return f'a{i // 2}' if i % 2 == 0 else f'w{i // 2}'


def core_connections(n, prefix='x'):
    return ', '.join(f'.{port(i)}({prefix}{i})' for i in range(n))


def connections(n):
    return ', '.join(f'.x{i}(x{i})' for i in range(n))


def wrapper(case, latency=4):
    w, n, core_latency = case['width'], len(case['coefficients']), case['core_latency']
    if not 0 <= core_latency < latency:
        raise ValueError('Core must fit within the external latency after the input register')
    ports = ', '.join(f'input signed [{w-1}:0] x{i}' for i in range(n))
    lines = [f'module dut(input clk, rst_n, {ports}, output [{w-1}:0] result);']
    for i in range(n):
        lines.extend([f'reg signed [{w-1}:0] q{i};',
                      f'always @(posedge clk) if (!rst_n) q{i} <= 0; else q{i} <= x{i};'])
    clocks = '.clk(clk), .rst_n(rst_n), ' if core_latency else ''
    lines.extend([f'wire [{w-1}:0] raw;',
                  f'kernel core({clocks}{core_connections(n, "q")}, .result(raw));'])
    signal = 'raw'
    for i in range(latency - 1 - core_latency):
        lines.extend([f'reg [{w-1}:0] pad{i};',
                      f'always @(posedge clk) if (!rst_n) pad{i} <= 0; else pad{i} <= {signal};'])
        signal = f'pad{i}'
    lines.extend([f'assign result = {signal};', 'endmodule'])
    return '\n'.join(lines) + '\n'


def reference(case):
    # Deliberately independent of the egraph, templates, CSD, and scheduling.
    return ' + '.join(f"($signed(x{i}) * 32'sh{c & 0xffffffff:08x})"
                      for i, c in enumerate(case['coefficients']))


def formal(case, work, sequential, timeout, latency=4):
    w, n = case['width'], len(case['coefficients'])
    ports = ', '.join(f'input signed [{w-1}:0] x{i}' for i in range(n))
    lines = [f'module miter(input clk, rst_n, {ports}, output ok);',
             f'wire [{w-1}:0] actual, ref_value;']
    if sequential:
        lines.extend([
            f'source src({core_connections(n)}, .result(ref_value));',
            f'dut impl(.clk(clk), .rst_n(rst_n), {connections(n)}, .result(actual));',
            f'reg [{w-1}:0] history [0:{latency-1}];',
            f"reg [{latency-1}:0] valid = 0; reg reset_seen = 0; integer i;",
            'always @(posedge clk) begin',
            '  reset_seen <= !rst_n;',
            '  if (!rst_n) begin',
            f'    valid <= 0; for (i=0; i<{latency}; i=i+1) history[i] <= 0;',
            "  end else begin valid <= (valid << 1) | 1'b1;",
            '    history[0] <= ref_value;',
            f'    for (i=1; i<{latency}; i=i+1) history[i] <= history[i-1];',
            '  end', 'end',
            f'assign ok = (!valid[{latency-1}] || actual == history[{latency-1}]) && (!reset_seen || actual == 0);',
        ])
    else:
        lines.extend([f'assign ref_value = {reference(case)};',
                      f'source impl({core_connections(n)}, .result(actual));',
                      'assign ok = actual == ref_value;'])
    lines.append('endmodule')
    (work / 'miter.sv').write_text('\n'.join(lines) + '\n')
    if sequential:
        # Preserve word-level structure. Bit-blasted induction was needlessly
        # expensive for the same exact pipeline/source arithmetic.
        (work / 'miter.sv').write_text('\n'.join(lines[:-1] + ['always @* assert(ok);', 'endmodule']) + '\n')
        script = ('read_verilog -formal -sv source.sv kernel.sv top.sv miter.sv\n'
                  'prep -top miter\nasync2sync\ndffunmap\nwrite_smt2 -wires miter.smt2\n')
        (work / 'formal.ys').write_text(script)
        _, seconds = checked(['yosys', '-Q', '-T', '-s', 'formal.ys'], work, 'formal-generation.log')
        combined = []
        steps = latency + 2
        for phase, options in [('base', ['--presat']), ('induction', ['-i'])]:
            cmd = ['yosys-smtbmc', '-s', 'bitwuzla', '-t', str(steps), '--timeout', str(timeout),
                   '--dump-vcd', f'counterexample-{phase}.vcd', *options, 'miter.smt2']
            output, code, elapsed = run(cmd, work, f'formal-{phase}.log', timeout + 15)
            seconds += elapsed
            combined.append((work / f'formal-{phase}.log').read_text())
            (work / 'formal.log').write_text('\n'.join(combined))
            if code == 0 and 'Status: PASSED' in output:
                continue
            if 'timeout' in output.lower() or 'timed out' in output.lower():
                return {'status': 'timeout', 'seconds': round(seconds, 3), 'method': 'smtbmc-bitwuzla-k-induction'}
            raise RuntimeError(f'Formal failure (not a timeout): {work / "formal.log"}\n{output[-1800:]}')
        return {'status': 'proved', 'seconds': round(seconds, 3), 'method': 'smtbmc-bitwuzla-k-induction', 'base_steps': steps, 'induction_depth_limit': steps}
    reads = 'read_verilog -sv source.sv\n'
    proof = f'sat -prove ok 1 -verify -timeout {timeout} -dump_vcd counterexample.vcd'
    script = reads + 'read_verilog -sv miter.sv\nprep -top miter -flatten\ntechmap\nopt\ncheck -assert\n' + proof + '\n'
    (work / 'formal.ys').write_text(script)
    output, code, seconds = run(['yosys', '-Q', '-T', '-s', 'formal.ys'], work, 'formal.log', timeout * 3 + 30)
    marker = 'SAT proof finished - no model found: SUCCESS!'
    if code == 0 and marker in output:
        status = 'proved'
    elif 'timeout' in output.lower() or 'timed out' in output.lower():
        status = 'timeout'
    else:
        raise RuntimeError(f'Formal failure (not a timeout): {work / "formal.log"}\n{output[-1800:]}')
    return {'status': status, 'seconds': seconds, 'method': 'combinational-SAT'}


def linear_formal(case, work):
    script = ('read_verilog -sv source.sv\nhierarchy -check -top source\n'
              'check -assert\nwrite_json source.json\n')
    (work / 'frontend.ys').write_text(script)
    _, seconds = checked(['yosys', '-Q', '-T', '-s', 'frontend.ys'], work, 'frontend.log')
    certificate = linear_check.check(json.loads((work / 'source.json').read_text()),
                                     case['width'], case['coefficients'])
    certificate['rtl_sha256'] = digest((work / 'source.sv').read_bytes())
    certificate['netlist_sha256'] = digest((work / 'source.json').read_bytes())
    dump(work / 'certificate.json', certificate)
    return {'status': 'proved', 'seconds': seconds, 'method': certificate['method']}


def simulate(case, work, latency=4):
    w, n = case['width'], len(case['coefficients'])
    mask = (1 << w) - 1
    edges = [0, 1, mask, 1 << (w-1), (1 << (w-1))-1, mask-1]
    values = [tuple([v]*n) for v in edges]
    for i in range(n):
        for v in edges:
            values.append(tuple(v if j == i else 0 for j in range(n)))
    rng = random.Random(SEED)
    values += [tuple(rng.getrandbits(w) for _ in range(n)) for _ in range(2048)]
    packed = []
    for xs in values:
        signed = [x-(1 << w) if x & (1 << (w-1)) else x for x in xs]
        expected = sum(x*c for x, c in zip(signed, case['coefficients'])) & mask
        bits = 0
        for x in xs:
            bits = (bits << w) | x
        bits = (bits << w) | expected
        packed.append(f'{bits:0{((n+1)*w+3)//4}x}')
    (work / 'vectors.hex').write_text('\n'.join(packed) + '\n')
    regs = '\n'.join(f'reg [{w-1}:0] x{i};' for i in range(n))
    unpack = ', '.join([f'x{i}' for i in range(n)] + ['expected'])
    tb = f'''module tb;
{regs}
reg clk=0, rst_n=0;
wire [{w-1}:0] actual;
reg [{w-1}:0] expected, history[0:{latency-1}];
reg [{(n+1)*w-1}:0] vectors[0:{len(values)-1}];
integer i, filled=0, checked=0;
dut impl(.clk(clk), .rst_n(rst_n), {connections(n)}, .result(actual));
initial begin
  $readmemh("vectors.hex", vectors);
  {{{unpack}}} = vectors[0];
  #5; clk=1; #1;
  if (actual !== 0) $fatal(1, "MISMATCH initial reset");
  clk=0; #4;
  for (i=0; i<{len(values)+latency-1}; i=i+1) begin
    if (i == {len(values)//2}) begin
      rst_n=0; #5; clk=1; #1;
      if (actual !== 0) $fatal(1, "MISMATCH reset");
      clk=0; #4; filled=0;
    end
    rst_n=1;
    {{{unpack}}} = vectors[i < {len(values)} ? i : 0];
    history[i % {latency}] = expected;
    #5; clk=1; #1;
    if (filled<{latency}) filled=filled+1;
    if (filled=={latency}) begin
      if (actual !== history[(i+1)%{latency}]) $fatal(1, "MISMATCH i=%0d got=%h expected=%h", i, actual, history[(i+1)%{latency}]);
      checked=checked+1;
    end
    clk=0; #4;
  end
  $display("SIM_PASS checked=%0d", checked); $finish;
end
endmodule
'''
    (work / 'tb.sv').write_text(tb)
    checked(['iverilog', '-g2012', '-s', 'tb', '-o', 'sim.vvp', 'kernel.sv', 'top.sv', 'tb.sv'], work, 'compile.log')
    output, seconds = checked(['vvp', 'sim.vvp'], work, 'simulation.log')
    count = int(re.search(r'SIM_PASS checked=(\d+)', output).group(1))
    if count != len(values) - (latency - 1):
        raise RuntimeError('Missing simulation comparisons')
    return {'comparisons': count, 'seconds': seconds}


def cached(out, category, key, task):
    work = out / category / key
    with LOCK_GUARD:
        lock = LOCKS.setdefault(str(work), threading.Lock())
    with lock:
        work.mkdir(parents=True, exist_ok=True)
        result_file = work / 'result.json'
        if result_file.exists():
            return json.loads(result_file.read_text())
        result = {**task(work), 'artifact': str(work.relative_to(out))}
        dump(result_file, result)
        return result


def measure(case, core, top, out, config, mapping):
    key = digest([core, top, mapping, config['tools']])

    def synth(work):
        (work / 'kernel.sv').write_text(core)
        (work / 'top.sv').write_text(top)
        script = 'read_verilog -sv kernel.sv top.sv\n'
        script += f'synth_ecp5 -top dut -json netlist.json {"-nodsp" if mapping == "nodsp" else ""}\n'
        script += 'check -assert\ntee -o stat.json stat -json\n'
        (work / 'synth.ys').write_text(script)
        _, seconds = checked(['yosys', '-Q', '-T', '-s', 'synth.ys'], work, 'synthesis.log')
        stats = json.loads((work / 'stat.json').read_text())['modules']['\\dut']['num_cells_by_type']
        return {'seconds': seconds, 'cells': stats, 'netlist_sha256': digest((work / 'netlist.json').read_bytes())}

    synthesis = cached(out, 'synthesis', key, synth)
    netlist = out / synthesis['artifact'] / 'netlist.json'
    routes = []
    for seed in config['pnr_seeds']:
        route_key = digest([synthesis['netlist_sha256'], config['device'], config['frequency_mhz'], seed, config['tools']])

        def route(work):
            # Route inputs are immutable. Sharing their inode avoids storing
            # the same mapped netlist once per seed; replay inputs remain local.
            target = work / 'netlist.json'
            target.unlink(missing_ok=True)
            try:
                os.link(netlist, target)
            except OSError:
                shutil.copyfile(netlist, target)
            cmd = ['nextpnr-ecp5', '--25k', '--package', 'CABGA381', '--speed', '6',
                   '--json', 'netlist.json', '--seed', str(seed), '--freq', str(config['frequency_mhz']),
                   '--lpf-allow-unconstrained', '--timing-allow-fail', '--report', 'timing.json']
            output, seconds = checked(cmd, work, 'pnr.log', timeout=180)
            report = json.loads((work / 'timing.json').read_text())
            fmax = report.get('fmax', {})
            if len(fmax) != 1 or 'Program finished normally.' not in output:
                raise RuntimeError(f'Missing single-clock routed timing: {work}')
            mhz = next(iter(fmax.values()))['achieved']
            return {'seed': seed, 'fmax_mhz': mhz, 'seconds': seconds, 'utilization': report['utilization']}

        routes.append(cached(out, 'route', route_key, route))
    return {'mapping': mapping, 'synthesis': synthesis, 'routes': routes,
            'worst_fmax_mhz': min(r['fmax_mhz'] for r in routes)}


def evaluate(case, aliases, out, config):
    source = (out / 'rtl' / (case['name'] + '_source.sv')).read_text()
    core = (out / 'rtl' / (case['name'] + '.sv')).read_text()
    latency = config['latency']
    top = wrapper(case, latency)
    source_key = digest([source, case['coefficients'], case['width'], config['formal_timeout'], config['tools']])

    def prove_source(work):
        (work / 'source.sv').write_text(source)
        return linear_formal(case, work)

    source_proof = cached(out, 'source_proof', source_key, prove_source)
    rtl_key = digest([core, top, source, case['coefficients'], config['formal_timeout'], config['tools']])

    def verify(work):
        (work / 'kernel.sv').write_text(core)
        (work / 'top.sv').write_text(top)
        (work / 'source.sv').write_text(source)
        simulation = simulate(case, work, latency)
        proof = formal(case, work, True, config['formal_timeout'], latency)
        return {'simulation': simulation, 'formal': proof}

    verification = cached(out, 'verification', rtl_key, verify)
    result = {'case': case['case'], 'width': case['width'], 'coefficients': case['coefficients'],
              'rtl_sha256': digest((core + top).encode()), 'aliases': aliases,
              'source_proof': source_proof, 'verification': verification, 'measurements': []}
    if source_proof['status'] == 'proved' and verification['formal']['status'] == 'proved':
        result['status'] = 'proved'
        for mapping in ['auto', 'nodsp']:
            result['measurements'].append(measure(case, core, top, out, config, mapping))
    else:
        result['status'] = 'unproved-timeout'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build' / 'explore')
    parser.add_argument('--filter', default='')
    parser.add_argument('--cases', type=Path, help='custom TSV: case, width, coefficients')
    parser.add_argument('--balanced-digits', action='store_true', help='also search balanced signed-digit multiplier trees (post-holdout extension)')
    parser.add_argument('--latency', type=int, default=4, choices=range(2, 17),
                        help='external cycles including input register and padding (default: 4)')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--seeds', default='1,2,3')
    parser.add_argument('--formal-timeout', type=int, default=45)
    parser.add_argument('--frequency', type=float, default=150.0)
    args = parser.parse_args()
    seeds = list(map(int, args.seeds.split(',')))
    if (args.jobs < 1 or args.formal_timeout < 1 or not math.isfinite(args.frequency)
            or args.frequency <= 0 or len(set(seeds)) != len(seeds)
            or not seeds or any(s < 0 or s >= 2**32 for s in seeds)):
        parser.error('require positive jobs/timeout/frequency and distinct unsigned 32-bit seeds')
    case_data = args.cases.read_bytes() if args.cases else None
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    tools = {}
    for exe, opt in [('yosys', '-V'), ('nextpnr-ecp5', '--version'), ('iverilog', '-V'), ('rustc', '--version'), ('bitwuzla', '--version')]:
        text, _ = checked([exe, opt], out, f'version-{exe}.log')
        tools[exe] = text.strip().splitlines()[0]
    sources = sorted((ROOT / 'hwine-rs/src').rglob('*.rs')) + [ROOT / p for p in
              ['tools/explore.py', 'tools/linear_check.py', 'hwine-rs/examples/explore_fixtures.rs',
               'hwine-rs/Cargo.toml', 'hwine-rs/Cargo.lock', 'rust-toolchain.toml']]
    config = {'device': 'LFE5U-25F-6 CABGA381', 'frequency_mhz': args.frequency,
              'pnr_seeds': seeds, 'formal_timeout': args.formal_timeout,
              'simulation_seed': SEED, 'tools': tools, 'scope_filter': args.filter,
              'case_manifest': {'filename': args.cases.name, 'sha256': digest(case_data)} if case_data is not None else None,
              'candidate_options': {'balanced_digits': args.balanced_digits},
              'latency': args.latency, 'initiation_interval': 1,
              'source_sha256': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sources}}
    # Driver changes invalidate result caches rather than silently reusing old
    # checks or experimental policies. Source RTL itself is also in each key.
    config['tools']['experiment_driver_sha256'] = digest([config['source_sha256'][p]
                                                        for p in ['tools/explore.py', 'tools/linear_check.py']])
    # Cargo can consider another checkout's same-named package fresh in a
    # shared target directory based on timestamps. Isolate by actual source
    # content, so a differently edited generator cannot reuse that executable.
    fingerprint = digest([config['source_sha256'], tools['rustc']])
    target_root = Path(os.environ.get('CARGO_TARGET_DIR', ROOT / 'hwine-rs/target')).resolve()
    generator_target = target_root / 'hwine-generators' / fingerprint
    config['generator'] = {'source_fingerprint': fingerprint, 'target_isolated_by_source_content': True}
    (out / 'summary.json').unlink(missing_ok=True)
    dump(out / 'config.json', config)
    custom = []
    if case_data is not None:
        (out / 'cases.tsv').write_bytes(case_data)
        custom = [str(out / 'cases.tsv')]
    if args.balanced_digits:
        custom.append('--balanced-digits')
    if args.latency != 4:
        custom.extend(['--latency', str(args.latency)])
    checked(['cargo', 'run', '--locked', '--manifest-path', str(ROOT / 'hwine-rs/Cargo.toml'),
             '--target-dir', str(generator_target), '--example', 'explore_fixtures', '--', str(out / 'rtl'), *custom],
            ROOT, str(out / 'generation.log'))
    manifest = list(csv.DictReader((out / 'rtl/manifest.tsv').open(), delimiter='\t'))
    unique = {}
    for c in manifest:
        if args.filter and args.filter not in c['case']:
            continue
        c['width'], c['core_latency'], c['interval'] = int(c['width']), int(c['core_latency']), int(c['interval'])
        c['coefficients'] = list(map(int, c['coefficients'].split(',')))
        core = (out / 'rtl' / (c['name'] + '.sv')).read_text()
        key = digest([c['case'], core, wrapper(c, args.latency)])
        if key not in unique:
            unique[key] = [c, []]
        unique[key][1].append({k: c[k] for k in ['name', 'style', 'group', 'interval', 'core_latency', 'estimated_delay']})
    if not unique:
        raise RuntimeError('No cases selected')
    print(f'{len(unique)} unique RTLs; {len({x[0]["case"] for x in unique.values()})} cases; seeds={config["pnr_seeds"]}', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(evaluate, c, aliases, out, config): c['name'] for c, aliases in unique.values()}
        for future in as_completed(futures):
            record = future.result()
            results.append(record)
            dump(out / 'progress.json', {'config': config, 'results': results})
            print(f'{len(results)}/{len(unique)} {futures[future]} {record["status"]}', flush=True)
    results.sort(key=lambda r: (r['case'], r['rtl_sha256']))
    dump(out / 'summary.json', {'status': 'complete', 'config': config, 'results': results})
    print(f'COMPLETE: {out / "summary.json"}', flush=True)


if __name__ == '__main__':
    main()
