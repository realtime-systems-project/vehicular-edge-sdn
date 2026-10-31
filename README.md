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

Private explanatory notes, project requirements, guide PDFs, sandbox results,
and local submission bundles are excluded from Git. The SUMO usage guide below
is shared with the SUMO integration code.
The Phase 1 baseline is preserved by the `phase1-baseline` tag.

## SUMO Integration

SUMO handles road traffic and physical provider movement; Python retains tasks,
offloading, queues, SDN, and Kalman estimation.
See the **[SUMO setup and usage guide](sumo_experiment/README.md)** for installation,
architecture, outputs, and troubleshooting.

With SUMO installed, run the compact town demo: **40 cars, 12 providers, and
8 edge servers** on a roughly 670 x 710 m OpenStreetMap network.

```bash
python3 run_sumo.py --map dinkelsbuhl --scenario demo --episodes 2 --steps 300 --gui --gui-delay-ms 200
```

The first GUI is the **baseline**: providers stay parked and there are no yellow
targets. The second is **controlled**: providers drive toward yellow destinations.
Cyan = cars, orange = providers, green = edge servers. The original course
scenarios and benchmark outputs are unchanged; the demo is not a performance claim.
