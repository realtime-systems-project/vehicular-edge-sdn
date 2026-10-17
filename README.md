# Vehicular Edge SDN

Real-time systems course project by Sobhan Aghasi Zadeh and Parmis Hemasian.
A Python simulator for provider-vehicle placement and task offloading in
vehicular edge computing.

Phase 1 provides random placement and scored offloading. Phase 2 adds SDN
placement strategies, a lightweight PPO-style strategy policy, and scalar
Kalman link-loss estimation. This is a simplified simulation: it does not
implement full neural PPO or learned CTDE offloading policies.

## Run

The original simulator needs Python 3.9+ and no external dependencies.
Run from the repository root:

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
- [`reports/`](reports/): Word report, PDFs, and LaTeX source.

Guides, project requirements, sandbox experiments, and local submission bundles
are excluded from Git.
The Phase 1 baseline is preserved by the `phase1-baseline` tag.

## SUMO Experiment

On the `codex/sumo-experiment` branch, SUMO supplies road traffic, signals, and
physical provider movement. Python retains task offloading, Kalman estimation,
and the existing PPO-style controller. Install SUMO and set `SUMO_HOME` to its
folder, then run:

```bash
python3 -m pip install -r requirements-sumo.txt
python3 run_sumo.py --scenario 1 --episodes 2 --steps 60
```

Add `--gui` to watch evaluation. Results, traffic files, and diagnostics go to a
fresh folder under `sandbox/sumo/`; original benchmark outputs stay unchanged.
