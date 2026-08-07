# Complete Project Flow

This file explains the full project flow, from running the baseline to running
the Phase 2 SDN/PPO/Kalman comparison.

## 1. Run The Baseline

Run:

```bash
python3 run_phase1.py
```

This runs the Phase 1 baseline for both required scenarios:

```text
Scenario 1: 20 vehicles, 3 provider vehicles, 2 edge servers
Scenario 2: 50 vehicles, 6 provider vehicles, 4 edge servers
```

## 2. Run The Full Phase 2 Method

Run:

```bash
python3 run_phase2.py
```

This runs:

1. the random-placement baseline
2. the SDN/PPO/Kalman method
3. the final comparison plots

## 3. Load Configuration

`run_phase1.py` reads the scenario definitions and simulation parameters from:

```text
phase1/config.py
```

This file defines values such as:

- map size
- number of simulation steps
- vehicle speed
- task size range
- compute power
- radio ranges
- bandwidths
- packet-loss weights

So before the simulation starts, all required parameters are known.

`run_phase2.py` also reads `Phase2Config`, which contains:

- PPO training episodes
- SDN update interval
- Kalman noise values
- reward weights
- Phase 2 offloading weights

## 4. Create The Environment

For each scenario, the code creates a `SimulationEnvironment`.

The environment contains:

- normal vehicles
- provider vehicles
- fixed edge servers
- traffic hotspots
- weather state

Normal vehicles are placed randomly and move during the simulation. Edge servers
are fixed. Provider vehicles are placed randomly because Phase 1 asks for random
placement.

## 5. Random Provider Placement

Provider vehicles are placed by:

```text
phase1/placement.py
```

For each provider vehicle:

```text
x = random position in map width
y = random position in map height
```

So each provider starts somewhere inside the two-dimensional area.

This is used as the baseline method.

## 6. Phase 2 SDN Placement

In Phase 2, provider placement is controlled by the SDN controller.

Every `10` simulation steps, the controller observes:

- demand center
- weather
- Kalman link-loss estimate
- provider queue pressure

Then it chooses a placement strategy and moves provider vehicles toward the new
coordinates.

## 7. Kalman Link Estimation

For each wireless link, the simulator computes a raw packet-loss value.

Phase 2 treats that raw value as a noisy measurement and updates a Kalman
filter.

The offloader then uses the Kalman estimate:

```text
raw packet loss -> noisy measurement -> Kalman filter -> predicted packet loss
```

## 8. Simulation Steps

The simulation runs for `120` steps by default.

At each step:

1. Generate tasks.
2. Update SDN placement if this is a large-timescale step.
3. Estimate link quality with Kalman filters.
4. Offload each task.
5. Save metrics.
6. Move vehicles.
7. Update queues.
8. Maybe update weather.

## 9. Task Generation

At each step, every normal vehicle has a chance to generate a task.

A task has:

- data size
- compute cycles
- deadline
- source vehicle id

Example:

```text
vehicle 7 creates task 43
task size = 4.2 Mbits
compute = 1.8 G cycles
deadline = 1.1 seconds
```

## 10. Build Offloading Options

For each task, the offloader checks possible choices:

1. Process locally on the vehicle.
2. Send directly to a provider vehicle.
3. Send directly to an edge server.
4. Send to a provider, then the provider forwards to an edge server.

Local processing is always possible. Remote options are possible only if the
nodes are in radio range.

## 11. Action Masking

Invalid choices are removed before scoring.

For example:

```text
vehicle -> provider
```

is valid only if:

```text
distance(vehicle, provider) <= vehicle_to_provider_range
```

If the provider is too far away, that option is not added.

The same idea is used for:

- vehicle to edge
- provider to edge

So the algorithm never chooses impossible routes. This is the simple Phase 1
version of action masking.

## 12. Estimate Packet Loss

For every valid wireless link, the environment estimates packet loss.

Packet loss depends on:

- distance
- traffic density
- weather

Simplified idea:

```text
packet loss = base loss + distance effect + traffic effect + weather effect
```

A longer link, crowded area, or bad weather gives higher packet loss.

## 13. Estimate Delay

Each candidate gets a delay.

For local processing:

```text
delay = queue time at vehicle + compute time
```

For remote processing:

```text
delay = transmission delay + queue time at destination + compute time
```

Transmission delay includes the expected effect of retransmissions. If packet
loss is high, expected retransmissions increase, so delay increases.

## 14. Score Each Candidate

Each candidate gets a score:

```text
score = delay + loss_weight * packet_loss + deadline_penalty
```

Meaning:

```text
lower score = better
```

The score balances:

- delay
- packet loss
- deadline safety

If a candidate misses the deadline, it gets an extra penalty.

## 15. Choose The Best Candidate

The offloader selects the candidate with the lowest score.

So for each task, the final decision includes:

- destination: vehicle, provider, or edge
- route: local, vehicle-to-provider, vehicle-to-edge, or vehicle-provider-edge
- delay
- packet loss
- missed deadline status
- expected retransmissions

## 16. Update Queue

After choosing a destination, the simulator updates that node's queue.

Example:

```text
if task is sent to provider 2,
provider 2 queue increases
```

This matters because future tasks may wait longer if many tasks are sent to the
same node.

## 17. Count Blind Spots

A blind spot means:

```text
the vehicle has no valid remote offloading option
```

The vehicle can still process locally, but it cannot reach any provider or edge
server.

## 18. Save Step Metrics

At the end of each step, the simulator saves metrics such as:

- number of tasks
- average delay
- average packet loss
- expected retransmissions
- missed deadlines
- blind spots
- destination counts
- route counts

## 19. Advance The Environment

Then the environment advances:

- vehicles move
- queues decrease because time passes
- weather may change every 20 steps

After that, the next step begins.

## 20. Final Summary

After all steps finish, the simulator creates a summary for the scenario:

- total tasks
- average packet loss
- average delay
- total missed deadlines
- total blind spots
- average provider location
- destination counts
- route counts

## 21. Output Files

Phase 1 writes:

```text
outputs/phase1/summary.csv
outputs/phase1/steps_scenario_1.csv
outputs/phase1/steps_scenario_2.csv
```

Phase 2 writes:

```text
outputs/phase2/summary.csv
outputs/phase2/convergence.csv
outputs/phase2/steps_scenario_1_baseline.csv
outputs/phase2/steps_scenario_1_sdn_ppo_kalman.csv
outputs/phase2/steps_scenario_2_baseline.csv
outputs/phase2/steps_scenario_2_sdn_ppo_kalman.csv
```

Phase 2 plots are written under:

```text
outputs/phase2/plots/
```

## One-Sentence Summary

```text
create vehicles/providers/edges -> randomly place providers -> generate tasks
-> train SDN placement policy -> estimate link loss with Kalman filters
-> remove invalid routes -> estimate loss and delay -> choose lowest-score
offloading action -> update queues and metrics -> compare with baseline -> save
CSV and SVG outputs
```
