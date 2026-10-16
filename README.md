# Vehicular Edge SDN

Real-time systems course project by Sobhan Aghasi Zadeh and Parmis Hemasian.
A Python simulator for provider-vehicle placement and task offloading in
vehicular edge computing.

Phase 1 provides random placement and scored offloading. Phase 2 adds SDN
placement strategies, a lightweight PPO-style strategy policy, and scalar
Kalman link-loss estimation. This is a simplified simulation: it does not
implement full neural PPO or learned CTDE offloading policies.

## Run

Python 3.9+; no external dependencies. Run from the repository root:

```bash
python3 run_phase1.py
python3 run_phase2.py
```

Both commands run the two required scenarios. Existing Phase 2 results and
plots are in [`outputs/phase2/`](outputs/phase2/). To try a short run without
overwriting those results:

```bash
python3 run_phase2.py --episodes 2 --steps 10 --output sandbox/smoke
```

Use `--help` for scenario, seed, and output options. Runs replace CSV files
and, for Phase 2, SVG plots in the selected output directory.

## Files

- [`phase1/`](phase1/), [`phase2/`](phase2/): simulation and controller code.
- [`docs/requirements/`](docs/requirements/): original project instructions.
- [`reports/`](reports/): Word report, PDFs, and LaTeX source.

Explanatory guides, sandbox experiments, and local submission bundles are excluded from Git.
The Phase 1 baseline is preserved by the `phase1-baseline` tag.
