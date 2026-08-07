# Real-Time Course Project

This repository contains Project 11 for the real-time systems course: an
SDN-based vehicular edge computing simulator for provider vehicle placement and
task offloading.

Phase 1 implements:

- a two-dimensional simulation environment with vehicles, provider vehicles,
  fixed edge servers, weather, traffic density, and packet-loss estimates
- the two required scenarios from `project-english.md`
- random provider-vehicle placement
- a readable task-offloading baseline with action masking for out-of-range links
- CSV outputs for packet loss, delay, missed deadlines, blind spots, provider
  locations, destination choices, and route choices

Phase 2 adds:

- Kalman-based link-quality estimation for packet-loss prediction
- a lightweight PPO-style SDN controller for provider vehicle placement
- decentralized task offloading using Kalman predictions
- baseline-vs-SDN/RL comparison under both required scenarios
- final CSV files and SVG plots for the required metrics

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

Run the full Phase 2 comparison:

```bash
python3 run_phase2.py
```

Phase 2 outputs are written under `outputs/phase2/`.

The default Phase 2 run creates:

- `summary.csv`
- `convergence.csv`
- `steps_scenario_1_baseline.csv`
- `steps_scenario_1_sdn_ppo_kalman.csv`
- `steps_scenario_2_baseline.csv`
- `steps_scenario_2_sdn_ppo_kalman.csv`
- `plots/average_packet_loss.svg`
- `plots/average_delay.svg`
- `plots/missed_deadlines.svg`
- `plots/blind_spots.svg`
- `plots/average_provider_locations.svg`
- `plots/rl_convergence.svg`
