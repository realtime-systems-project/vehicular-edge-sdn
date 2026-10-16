# Project Explanation

This file is a compact presentation script for the full project.

## Project Goal

The project is about vehicular edge computing. Normal vehicles generate
computational tasks. These tasks can be processed on the vehicle itself, on a
provider vehicle, or on a fixed edge server.

The main goal is to reduce:

- packet loss
- delay
- missed deadlines
- blind spots

The project uses a two-timescale idea:

- large timescale: the SDN controller places provider vehicles
- small timescale: each vehicle decides task offloading and route selection

## Phase 1 Baseline

Phase 1 builds the baseline system.

It includes:

- a two-dimensional simulation environment
- the two required scenarios
- random provider vehicle placement
- a simple task-offloading algorithm
- CSV metrics

The Phase 1 offloader checks valid actions and chooses the action with the best
delay/loss/deadline score.

## Phase 2 Full Method

Phase 2 keeps the Phase 1 baseline and adds the full project method.

It includes:

- Kalman-based link-quality estimation
- SDN provider placement
- a small PPO-style policy update
- decentralized offloading using predicted packet loss
- final plots
- comparison with the baseline

## Scenarios

The project requires two scenarios:

| Scenario | Vehicles | Provider vehicles | Edge servers |
|---|---:|---:|---:|
| Scenario 1 | 20 | 3 | 2 |
| Scenario 2 | 50 | 6 | 4 |

Both scenarios are run for the baseline and the Phase 2 method.

## Environment

The environment is a `1000m x 1000m` two-dimensional area.

It contains:

- moving vehicles
- provider vehicles
- fixed edge servers
- traffic hotspots
- weather

Vehicles generate tasks during the simulation. Weather changes over time.
Traffic density depends on hotspots and nearby vehicles.

## Packet Loss

For each wireless link, the simulator first checks range.

If the receiver is outside radio range, the link is invalid.

If the link is valid, packet loss is estimated from:

- distance
- traffic density
- weather

The basic formula is:

```text
loss = base_loss + distance_effect + traffic_effect + weather_penalty
```

Phase 2 then sends this noisy link measurement through a Kalman filter, so the
offloader uses predicted packet loss instead of only the raw current value.

## Delay

For local processing:

```text
delay = queue time + compute time
```

For remote processing:

```text
delay = transmission delay + destination queue time + compute time
```

Transmission delay includes expected retransmissions:

```text
expected attempts = 1 / (1 - packet loss)
```

So higher packet loss increases effective transmission delay.

## Offloading

For each task, the vehicle checks:

- local processing
- direct provider offloading
- direct edge offloading
- provider-to-edge relay

Invalid routes are removed with action masking.

The offloader then scores valid candidates and chooses the lowest-score action.
In Phase 2, this score uses Kalman-predicted packet loss.

## SDN/PPO Placement

The SDN controller acts on the large timescale. Every few steps, it updates
provider vehicle positions.

The controller state includes:

- demand center
- weather effect
- average Kalman link-loss estimate
- provider queue pressure

The controller has several placement strategies:

- demand center
- coverage grid
- edge bridge
- loss-aware placement
- balanced grid
- capacity-demand clustering

During training, a PPO-style clipped update changes the probability of choosing
each strategy. The reward penalizes delay, packet loss, missed deadlines, and
blind spots.

## Outputs

Phase 2 writes:

```text
outputs/phase2/summary.csv
outputs/phase2/convergence.csv
outputs/phase2/steps_scenario_1_baseline.csv
outputs/phase2/steps_scenario_1_sdn_ppo_kalman.csv
outputs/phase2/steps_scenario_2_baseline.csv
outputs/phase2/steps_scenario_2_sdn_ppo_kalman.csv
```

It also writes plots:

```text
outputs/phase2/plots/average_packet_loss.svg
outputs/phase2/plots/average_delay.svg
outputs/phase2/plots/missed_deadlines.svg
outputs/phase2/plots/blind_spots.svg
outputs/phase2/plots/average_provider_locations.svg
outputs/phase2/plots/rl_convergence.svg
```

## Code Structure

- `phase1/config.py`: shared parameters
- `phase1/models.py`: data models
- `phase1/environment.py`: simulation world
- `phase1/placement.py`: random baseline placement
- `phase1/offloading.py`: task offloading and action masking
- `phase1/simulation.py`: Phase 1 runner helpers
- `phase2/kalman.py`: Kalman link-quality estimation
- `phase2/sdn_controller.py`: SDN/PPO-style provider placement
- `phase2/runner.py`: training, evaluation, and comparison
- `phase2/plotting.py`: SVG plots
- `run_phase1.py`: baseline entrypoint
- `run_phase2.py`: full project entrypoint

## Final Summary

The final implementation compares a random-placement baseline with an
SDN/PPO/Kalman method. The SDN controller places provider vehicles based on
traffic, weather, and Kalman link-quality estimates. Vehicles then make
decentralized offloading decisions using predicted packet loss and action
masking. The project outputs the required metrics and plots for both scenarios.

