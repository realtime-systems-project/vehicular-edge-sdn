# Real-Time Course Project - Phase 1

This repository contains the Phase 1 baseline for Project 11: an SDN-based
vehicular edge computing simulator.

Phase 1 implements:

- a two-dimensional simulation environment with vehicles, provider vehicles,
  fixed edge servers, weather, traffic density, and packet-loss estimates
- the two required scenarios from `project-english.md`
- random provider-vehicle placement
- a readable task-offloading baseline with action masking for out-of-range links
- CSV outputs for packet loss, delay, missed deadlines, blind spots, provider
  locations, destination choices, and route choices

Run both scenarios:

```bash
python3 run_phase1.py
```

Run a short smoke simulation:

```bash
python3 run_phase1.py --scenario 1 --steps 10 --seed 7
```

Outputs are written under `outputs/phase1/`.

The default run creates only three CSV files:

- `summary.csv`
- `steps_scenario_1.csv`
- `steps_scenario_2.csv`
