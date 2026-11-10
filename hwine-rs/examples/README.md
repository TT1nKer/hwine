# Example scope

The current acceptance path consists of:

- `stream_fir_bench`: emits a signed 16-bit, three-tap-tuple FIR datapath with
  balanced pipelining and reports its latency. Generated input ports `a0`, `w0`,
  `a1` correspond to the three tap samples; coefficients are internal constants.
- `validation_fixtures`: emits the deterministic integer/FIR implementation
  corpus consumed by `tools/validate.py`.
- `formal_equiv`: invokes the full independent RTL validation suite and propagates
  failure. It requires Icarus, Yosys and Python on PATH.

Other examples are retained historical experiments. They compile in CI but are
not executed there. Examples requesting unsupported atoms or implicit type/width
changes can now fail at checked RTL generation. Their old cost, timing and proof
labels are not current validated results. See the root README and
[semantics contract](../../docs/RELIABILITY.md).
