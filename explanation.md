# Phase 1 Explanation

This file is written as a compact presentation script. It explains what was
implemented, why it was implemented this way, and how the project is structured.

## Project Goal

The project is about vehicular edge computing. Normal vehicles create
computational tasks. These tasks can be processed locally, sent to mobile
provider vehicles, or sent to fixed edge servers.

The main objective is to reduce:

- packet loss
- system delay
- missed task deadlines
- blind spots

Phase 1 does not implement the final reinforcement learning method. Instead, it
builds the simulation environment and a clear baseline method.

## What Phase 1 Implements

Phase 1 implements four main parts:

1. A two-dimensional simulation environment.
2. Random placement for provider vehicles.
3. A task-offloading algorithm.
4. CSV outputs for the required metrics.

The implementation supports both required scenarios:

| Scenario | Vehicles | Provider vehicles | Edge servers |
|---|---:|---:|---:|
| Scenario 1 | 20 | 3 | 2 |
| Scenario 2 | 50 | 6 | 4 |

## Simulation Environment

The environment is a `1000m x 1000m` two-dimensional area.

It contains:

- normal vehicles
- provider vehicles
- fixed edge servers
- traffic hotspots
- weather states

Vehicles move during the simulation. Weather changes occasionally. Traffic
density is estimated from hotspots and nearby vehicles.

Packet-loss probability is computed from:

- distance between sender and receiver
- traffic density
- weather condition

If two nodes are outside radio range, the link is invalid.

## Random Provider Placement

Provider vehicles are placed randomly and uniformly in the map.

This satisfies the Phase 1 requirement and gives us a baseline. In Phase 2, this
part can be replaced by an SDN controller that learns better provider locations.

## Task Generation

At each simulation step, every vehicle may generate a task.

Each task has:

- input data size
- required CPU cycles
- deadline

These values are randomly generated inside configured ranges.

## Offloading Algorithm

For every task, the algorithm builds possible candidates:

- process locally on the vehicle
- send to a provider vehicle
- send directly to an edge server
- send to an edge server through a provider relay

Invalid candidates are removed. For example, if a provider is out of radio
range, that candidate is not considered.

For each valid candidate, the algorithm estimates:

- transmission delay
- processing delay
- packet-loss probability
- expected retransmissions
- whether the task misses its deadline

Then it computes a score:

```text
score = delay + loss_weight * packet_loss + deadline_penalty
```

The candidate with the smallest score is selected.

## Metrics

The simulator records:

- average packet-loss ratio
- average system delay
- number of missed deadlines
- number of blind-spot occurrences
- average provider vehicle position
- destination counts
- route counts

The results are written to CSV files under:

```text
outputs/phase1/
```

The main file is:

```text
outputs/phase1/summary.csv
```

The per-step files are:

```text
outputs/phase1/steps_scenario_1.csv
outputs/phase1/steps_scenario_2.csv
```

## Code Structure

The project code is split into small files:

- `phase1/config.py`: scenario and simulation parameters
- `phase1/models.py`: data models
- `phase1/environment.py`: world state, mobility, weather, traffic, packet loss
- `phase1/placement.py`: random provider placement
- `phase1/offloading.py`: task-offloading logic
- `phase1/simulation.py`: simulation loop and CSV output
- `run_phase1.py`: command-line runner

This structure keeps Phase 1 simple and makes Phase 2 easier. The learned SDN
placement policy can replace the random placement module, and the learned
offloading policy can replace the score-based offloader.

## Design Decisions

The code uses only the Python standard library.

This was chosen because Phase 1 should be easy to run, read, and present. It
also avoids dependency problems before the final learning and plotting phase.

The simulator uses dataclasses for clarity. Each important concept has a direct
model: task, vehicle, provider, edge server, link, candidate, decision, and
metrics.

The packet-loss model is simple but meaningful. It captures the three important
ideas from the project statement: distance, traffic, and weather.

The offloading algorithm is also simple but complete. It supports destination
selection and route selection, including relay routes through provider vehicles.

## How To Run

Run both required scenarios:

```bash
python3 run_phase1.py
```

Run only scenario 1:

```bash
python3 run_phase1.py --scenario 1
```

Run a short test:

```bash
python3 run_phase1.py --scenario 1 --steps 10
```

## Final Presentation Summary

In Phase 1, we implemented the baseline simulator for the SDN vehicular edge
computing project. The simulator creates vehicles, provider vehicles, edge
servers, weather, traffic, packet-loss estimates, and random tasks. Provider
vehicles are placed randomly as the baseline placement method. For every task,
the offloading algorithm checks all valid destinations and routes, removes
out-of-range actions, estimates delay and packet loss, and selects the candidate
with the lowest score. The simulator records all required Phase 1 metrics and
writes them to CSV files for later plotting and comparison in Phase 2.
