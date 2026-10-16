# Complete Project Flow

This file explains the important flows of the project from start to finish. It
covers the full Phase 2 path: scenario setup, baseline comparison, SDN placement,
PPO-style training, Kalman link estimation, task offloading, metric collection,
and output generation.

The goal is not to explain every helper line. The goal is to make the execution
flow understandable enough to present and defend.

## 1. Big Picture

The project simulates a vehicular edge-computing network.

There are three types of computing nodes:

- normal vehicles
- Provider Vehicles
- fixed Edge Servers

Normal vehicles generate computational tasks. Each task must be processed in one
of these ways:

```text
1. locally on the source vehicle
2. on a nearby Provider Vehicle
3. on a fixed Edge Server
4. through a Provider Vehicle relay, then on an Edge Server
```

The project tries to reduce:

- average packet loss
- average delay
- expected retransmissions
- missed deadlines
- blind spots

Phase 1 builds the baseline:

```text
random Provider Vehicle placement + score-based task offloading
```

Phase 2 keeps that baseline and adds:

```text
SDN controller + PPO-style placement learning + Kalman link-quality estimation
```

So the final comparison is:

```text
baseline_random       vs       sdn_ppo_kalman
```

## 2. Required Scenarios

The project has two required scenarios:

```text
Scenario 1:
    20 vehicles
    3 Provider Vehicles
    2 Edge Servers

Scenario 2:
    50 vehicles
    6 Provider Vehicles
    4 Edge Servers
```

Both scenarios are run with the same evaluation length by default:

```text
120 simulation steps
```

The default Phase 2 command is:

```bash
python3 run_phase2.py
```

This runs both scenarios and writes outputs to:

```text
outputs/phase2
```

## 3. Main Entry Flow

The execution starts from:

```text
run_phase2.py
```

Its main job is simple:

```python
args = parse_args()
scenario_ids = [1, 2] or one selected scenario
sim_config = SimulationConfig(seed=args.seed)
phase2_config = Phase2Config(
    training_episodes=args.episodes,
    evaluation_steps=args.steps,
)
run_phase2_for_scenarios(...)
print_summary(...)
```

Important command-line options:

```bash
python3 run_phase2.py --scenario all
python3 run_phase2.py --scenario 1
python3 run_phase2.py --scenario 2
python3 run_phase2.py --episodes 24
python3 run_phase2.py --steps 120
python3 run_phase2.py --seed 7
python3 run_phase2.py --output outputs/phase2
```

The default behavior is the full required Phase 2 run.

## 4. Configuration Flow

The configuration lives in:

```text
phase1/config.py
```

This file defines:

- scenario sizes
- map size
- simulation step count
- task-generation probability
- vehicle speed range
- compute power of vehicles/providers/edges
- wireless ranges
- bandwidths
- packet-loss/offloading weights
- Phase 2 SDN/PPO/Kalman parameters

Conceptually:

```text
SCENARIOS
    scenario_1 = 20 vehicles, 3 providers, 2 edges
    scenario_2 = 50 vehicles, 6 providers, 4 edges

SimulationConfig
    physical simulation and baseline offloading parameters

Phase2Config
    SDN update interval
    PPO training parameters
    Kalman noise values
    reward weights
    Phase 2 scoring weights
```

The important Phase 2 settings are:

```text
training_episodes = 24
sdn_update_interval_steps = 10
provider_move_fraction = 0.75
ppo_clip_epsilon = 0.20
kalman_process_noise = 0.004
kalman_measurement_noise = 0.035
kalman_measurement_jitter = 0.025
```

The SDN controller updates Provider Vehicle placement every 10 simulation steps.
Task offloading still happens every simulation step.

That is the two-timescale structure.

## 5. Environment Creation Flow

For each run, the code creates:

```text
SimulationEnvironment(scenario, config)
```

This happens in:

```text
phase1/environment.py
```

The environment owns the mutable world state:

```text
vehicles
Provider Vehicles
Edge Servers
traffic hotspots
weather
current simulation step
random generator
next task id
```

At initialization:

```python
self.vehicles = self._create_vehicles()
self.providers = random_provider_placement(...)
self.edge_servers = self._create_edge_servers()
self.hotspots = self._create_hotspots()
```

Normal vehicles are created with random initial positions, random speeds, and
random movement directions.

Provider Vehicles are initially placed randomly. In the baseline, they stay under
that random placement behavior. In Phase 2, the SDN controller later moves them.

Edge Servers are fixed near opposite sides of the map.

Traffic hotspots are fixed regions that make some areas busier than others.

## 6. World Update Flow

Every simulation step, the environment advances with:

```python
environment.advance()
```

This does four things:

```text
1. increase step index
2. maybe update weather
3. move vehicles
4. decay processing queues
```

The code flow is:

```python
self.step_index += 1
self._update_weather()
self._move_vehicles()
self._decay_queues(self.vehicles)
self._decay_queues(self.providers)
self._decay_queues(self.edge_servers)
```

Weather changes every 20 steps. The possible weather states are:

```text
clear
rain
fog
storm
```

Each weather state has a packet-loss penalty:

```text
clear -> 0.00
rain  -> 0.09
fog   -> 0.13
storm -> 0.22
```

Vehicles move according to speed and direction. A small random direction noise is
added, and vehicles bounce back from the map boundary.

Queues decay because time passes. If a node has queued processing work, one time
step reduces that queue.

## 7. Task Generation Flow

At every step, each normal vehicle may generate a task:

```python
tasks = environment.generate_tasks()
```

For each vehicle:

```python
if random_number <= task_probability_per_vehicle:
    create task
```

Each task contains:

```text
task_id
source vehicle id
created step
data size in Mbits
required compute cycles in G cycles
deadline in seconds
```

The task parameters are randomly sampled from configured ranges.

Example task:

```text
task_id = 43
vehicle_id = 7
data_size_mbits = 4.2
compute_cycles_g = 1.8
deadline_s = 1.1
```

This task must now be assigned to a processing destination.

## 8. Traffic And Packet-Loss Map Flow

The environment estimates local traffic with:

```python
environment.traffic_density_at(position)
```

Traffic density comes from two sources:

```text
1. static traffic hotspots
2. nearby vehicles within 150 meters
```

A crowded area means a noisier wireless channel.

Packet loss is computed with:

```python
environment.packet_loss_probability(source, target, radio_range_m)
```

The first check is range validity:

```python
if distance(source, target) > radio_range_m:
    return None
```

`None` means the link is impossible and must be masked out.

If the link is in range, packet loss is:

```text
loss = 0.02
     + 0.28 * distance_ratio^2
     + 0.18 * traffic
     + weather_penalty
```

where:

```text
distance_ratio = distance / radio_range
traffic = average traffic density around source and target
```

Then the result is clamped:

```text
0.01 <= loss <= 0.85
```

This means distance matters mainly because it increases packet loss and can make
links invalid. Propagation delay itself is ignored because over a 1000 meter map
it is tiny compared with transmission, queueing, processing, and retransmission
delay.

## 9. Baseline Simulation Flow

The baseline is run by:

```text
phase1/simulation.py -> run_simulation(...)
```

For each scenario:

```python
environment = SimulationEnvironment(scenario, config)
offloader = TaskOffloader(config)

for each step:
    tasks = environment.generate_tasks()
    decisions = [offloader.decide(task, environment) for task in tasks]
    step_metrics.append(_summarize_step(environment, decisions))
    environment.advance()
```

The baseline uses:

```text
random Provider Vehicle placement
raw packet-loss values
score-based offloading
```

It does not use SDN placement, PPO training, or Kalman filtering.

The baseline is still important because Phase 2 must compare the final method
against a base method.

## 10. Phase 2 Top-Level Flow

Phase 2 is run by:

```text
phase2/runner.py -> run_phase2_for_scenarios(...)
```

For each required scenario, it performs this sequence:

```python
baseline = run_simulation(..., method_name="baseline_random")

controller, convergence = train_controller(...)

phase2_summary = evaluate_controller(..., controller)

write baseline step CSV
write Phase 2 step CSV
```

After all scenarios:

```python
write_summary_csv(...)
write_convergence_csv(...)
write_phase2_plots(...)
```

So Phase 2 always has a direct baseline-vs-method comparison.

## 11. SDN Controller Role

The SDN controller is the large-timescale decision-maker.

It does not decide every individual task. Instead, it periodically decides where
Provider Vehicles should move.

The controller code is in:

```text
phase2/sdn_controller.py
```

Its input state contains:

```text
demand_x
demand_y
weather_loss
average_kalman_loss
provider_queue
```

Meaning:

- `demand_x`, `demand_y`: where current demand is concentrated.
- `weather_loss`: how much the current weather hurts wireless links.
- `average_kalman_loss`: current learned estimate of link quality.
- `provider_queue`: how overloaded Provider Vehicles are.

This matches the project idea that the SDN controller should use traffic,
weather, and packet-loss information.

## 12. SDN Action Flow

The controller has a policy over placement actions.

The actions are:

```text
demand_center
coverage_grid
edge_bridge
loss_aware
balanced_grid
capacity_demand
```

Each action is a placement strategy.

### demand_center

Places Provider Vehicles around the current demand center.

Purpose:

```text
serve the busiest region directly
```

### coverage_grid

Spreads Provider Vehicles across the map.

Purpose:

```text
reduce blind spots and improve coverage
```

### edge_bridge

Places Provider Vehicles between demand and fixed Edge Servers.

Purpose:

```text
make Provider Vehicles useful as relay nodes toward Edge Servers
```

### loss_aware

Moves Provider Vehicles closer to demand when weather or Kalman packet loss is
high.

Purpose:

```text
shorten risky wireless links under bad link conditions
```

### balanced_grid

Keeps some providers near demand and spreads the rest across the map.

Purpose:

```text
balance demand service and coverage
```

### capacity_demand

Clusters Provider Vehicles near weighted vehicle demand.

Purpose:

```text
handle larger scenarios where demand may exist in several regions
```

Each action outputs continuous coordinates. The implementation uses strategies
instead of a large neural network so the method stays readable and dependency-free.

## 13. Provider Movement Flow

The controller does not teleport Provider Vehicles fully to the target.

Instead:

```text
new_position = current_position
             + provider_move_fraction * (target_position - current_position)
```

The configured value is:

```text
provider_move_fraction = 0.75
```

So a provider moves 75% of the way toward the selected target on each SDN update.

After that, the environment clips positions to the map boundary:

```python
environment.set_provider_positions(positions)
```

This keeps all Provider Vehicles inside the valid 2D area.

## 14. RL Meaning In This Project

RL means the SDN controller learns from reward.

In this project:

```text
agent       = SDN controller
environment = vehicular edge simulation
state       = demand/weather/Kalman/queue summary
action      = Provider Vehicle placement strategy
reward      = negative network cost
```

The controller repeatedly tries placement strategies. After each episode, it
sees how well the network performed.

Good performance means:

```text
lower delay
lower packet loss
fewer missed deadlines
fewer blind spots
```

Bad performance means the opposite.

The controller does not receive a perfect answer. It learns from measured
simulation results.

## 15. PPO-Style Training Flow

PPO means Proximal Policy Optimization.

The key idea is:

```text
update the policy, but do not let it change too aggressively in one episode
```

The controller stores one logit per placement action. Logits are converted into
probabilities by softmax:

```python
probability[action] = exp(logit[action]) / sum(exp(all logits))
```

During training:

```python
probabilities = controller._policy()
action = sample(probabilities)
positions = positions_for_action(action)
```

After the episode, a reward is computed. The controller also keeps a running
reward baseline.

```python
advantage = reward - reward_baseline
```

If advantage is positive, the sampled actions were better than usual. If it is
negative, they were worse than usual.

The PPO-style ratio is:

```python
ratio = current_probability / old_probability
```

Then it is clipped:

```python
clipped_ratio = clip(ratio, 1 - epsilon, 1 + epsilon)
```

The project uses:

```text
epsilon = 0.20
```

So the update is limited to a safe range.

Simple meaning:

```text
If an action helped, increase its probability.
If an action hurt, decrease its probability.
But change probabilities gradually.
```

The controller also applies a small entropy bonus. That nudges the policy toward
exploration so it does not collapse too early to one action.

## 16. Training Episode Flow

Training is done by:

```text
phase2/runner.py -> train_controller(...)
```

For each episode:

```python
episode_config = replace(
    sim_config,
    steps=phase2_config.evaluation_steps,
    seed=sim_config.seed + scenario.vehicle_count + episode * 17,
)

reward, decisions, summary = _run_controlled_episode(
    deterministic=False,
    method_name="sdn_ppo_kalman_train",
)

advantage = controller.update(decisions, reward)
```

The episode produces a convergence row:

```text
scenario
episode
reward
advantage
avg_packet_loss
avg_delay_s
missed_deadlines
blind_spots
best_action
```

These rows are written to:

```text
outputs/phase2/convergence.csv
```

They are also used for the RL convergence plot.

## 17. Controlled Episode Flow

The most important Phase 2 execution function is:

```text
_run_controlled_episode(...)
```

It creates:

```python
environment = SimulationEnvironment(scenario, sim_config)
estimator = LinkQualityEstimator(phase2_config)
offloader = TaskOffloader(sim_config, loss_estimator=estimator.estimate)
```

The key difference from baseline is this line:

```python
offloader = TaskOffloader(..., loss_estimator=estimator.estimate)
```

That means the offloader does not directly trust raw packet loss. It uses the
Kalman-smoothed packet-loss estimate.

Then each step runs:

```python
for each step:
    if step_index % sdn_update_interval == 0:
        choose or force SDN placement action
        environment.set_provider_positions(...)

    tasks = environment.generate_tasks()
    decisions = [offloader.decide(task, environment) for task in tasks]
    step_metrics.append(_summarize_controlled_step(environment, decisions))
    environment.advance()
```

This is the core Phase 2 loop.

## 18. Kalman Link Estimation Flow

Kalman link estimation is implemented in:

```text
phase2/kalman.py
```

The project asks vehicles to estimate link quality and predict packet loss. In
our implementation, every directed wireless link gets one scalar Kalman filter.

A link key looks like:

```text
("vehicle:7", "provider:2")
("provider:2", "edge:0")
("vehicle:4", "edge:1")
```

The hidden state is:

```text
current packet-loss probability of that link
```

The measurement is:

```text
raw packet loss + random measurement noise
```

The update flow is:

```python
measurement = true_loss + gaussian_noise
filter = filters[(source_id, target_id)]
estimate = filter.update(measurement)
```

Inside the scalar Kalman filter:

```python
predicted_uncertainty = uncertainty + process_noise
kalman_gain = predicted_uncertainty / (predicted_uncertainty + measurement_noise)
estimate = estimate + kalman_gain * (measurement - estimate)
uncertainty = (1 - kalman_gain) * predicted_uncertainty
```

The returned estimate is clamped:

```text
0.01 <= estimated_loss <= 0.85
```

Why this matters:

```text
raw wireless measurements can be noisy
Kalman smooths them
smoothed loss gives more stable offloading decisions
```

## 19. Task Offloading Flow

Task offloading is implemented in:

```text
phase1/offloading.py
```

The same offloader is used by both baseline and Phase 2.

Difference:

```text
baseline: uses raw environment packet loss
Phase 2: uses Kalman-estimated packet loss
```

For each task:

```python
candidates = self._build_candidates(task, environment)
best = min(candidates, key=lambda candidate: candidate.score)
self._apply_processing_load(best, environment)
```

So the offloader:

```text
1. builds all valid actions
2. scores every candidate
3. picks the lowest-score candidate
4. adds processing load to the selected node
```

## 20. Candidate Construction Flow

The offloader always adds local processing:

```text
vehicle -> same vehicle
```

Then it checks remote options:

```text
vehicle -> provider
vehicle -> edge
vehicle -> provider -> edge
```

The route names are:

```text
local
vehicle_to_provider
vehicle_to_edge
vehicle_provider_edge
```

For each possible wireless hop, `_make_link(...)` is called.

If `_make_link(...)` returns `None`, the route is impossible and is not added.

This is action masking.

## 21. Action Masking Flow

Action masking means invalid actions are removed before scoring.

Example:

```python
raw_loss = environment.packet_loss_probability(source, target, radio_range)
if raw_loss is None:
    return None
```

A route is valid only if all required hops are in range.

For direct provider processing:

```text
vehicle -> provider must be in range
```

For direct edge processing:

```text
vehicle -> edge must be in range
```

For provider-to-edge routing:

```text
vehicle -> provider must be in range
provider -> edge must be in range
```

If either hop is invalid, the route is removed.

This prevents impossible network actions.

## 22. Link Delay And Retransmission Flow

For every valid wireless link:

```python
expected_attempts = 1 / (1 - loss)
expected_retransmissions = expected_attempts - 1
tx_delay = (task.data_size_mbits / bandwidth_mbps) * expected_attempts
```

So packet loss increases transmission delay.

Example:

```text
loss = 0.00 -> expected attempts = 1.00
loss = 0.20 -> expected attempts = 1.25
loss = 0.50 -> expected attempts = 2.00
```

This is why packet loss affects both:

```text
average packet loss
average delay
```

## 23. Local Candidate Flow

Local processing has no wireless link.

```python
processing_delay = vehicle_queue + task_compute_cycles / vehicle_compute_power
packet_loss = 0
expected_retransmissions = 0
```

Local processing is always valid.

It may still miss the deadline if the vehicle is slow or its queue is long.

## 24. Remote Candidate Flow

Remote processing uses one or more wireless links.

```python
processing_delay = destination_queue + task_compute_cycles / destination_compute_power
tx_delay = sum(link.tx_delay_s for link in links)
loss_probability = 1 - product(1 - link.loss for each link)
total_delay = tx_delay + processing_delay
```

For a two-hop route:

```text
vehicle -> provider -> edge
```

The final route packet loss is the probability that at least one hop fails:

```text
combined_loss = 1 - (1 - loss_hop_1) * (1 - loss_hop_2)
```

## 25. Scoring Flow

Every candidate gets a score:

```python
score = delay + loss_weight * packet_loss + deadline_penalty
```

Deadline penalty is:

```python
if delay > deadline:
    deadline_penalty = deadline_weight * (delay - deadline)
else:
    deadline_penalty = 0
```

Meaning:

```text
lower score is better
```

The score balances:

```text
delay
packet loss
deadline safety
```

Phase 2 uses stronger loss/deadline weights than the baseline. This makes the
system more careful about risky wireless routes.

That is why Phase 2 can reduce packet loss and retransmissions while sometimes
increasing average delay slightly.

## 26. Blind Spot Flow

A blind spot is counted when a task has no remote candidate.

In code:

```python
remote_candidates = [c for c in candidates if c.destination_type != "vehicle"]
blind_spot = len(remote_candidates) == 0
```

This means the source vehicle had to process locally because no Provider Vehicle
or Edge route was reachable.

Provider placement affects blind spots strongly. Better Provider positions create
more valid remote routes.

## 27. Queue Update Flow

After the best candidate is selected, the selected node receives processing load.

The destination can be:

```text
source vehicle
Provider Vehicle
Edge Server
```

The offloader updates that node's queue:

```python
node.queue_s += processing_time_of_new_task
```

Then, when the environment advances, queues decay by one simulation time step.

This creates realistic contention:

```text
a powerful Edge Server may still become slower if many tasks are assigned to it
```

## 28. Metric Collection Flow

Each step produces a `StepMetrics` object.

It stores:

```text
step
task_count
average_delay_s
average_packet_loss
expected_retransmissions
missed_deadlines
blind_spots
average_provider_x
average_provider_y
destination_counts
route_counts
```

The step-level averages are calculated only over tasks generated in that step.

At the end of a scenario, the code builds a `SimulationSummary`.

Whole-run metrics include:

```text
total tasks
weighted average delay
weighted average packet loss
total expected retransmissions
total missed deadlines
total blind spots
merged destination counts
merged route counts
```

Weighted averages are used because some steps generate more tasks than others.

## 29. Reward Flow

The SDN controller reward is computed from the final summary of an episode.

```python
reward = -(
    delay_weight * average_delay
  + loss_weight * average_packet_loss
  + deadline_weight * missed_deadlines / task_count
  + blind_spot_weight * blind_spots / task_count
)
```

The reward is negative cost.

So:

```text
lower cost -> less negative reward -> better
higher cost -> more negative reward -> worse
```

The reward includes normalized deadline and blind-spot terms so scenarios with
different task counts are comparable.

## 30. Deterministic Evaluation Flow

After training, the project evaluates the trained controller.

The code does not rely only on the final sampled policy. It evaluates candidate
actions deterministically:

```python
candidate_actions = [controller.best_action_name(), *PLACEMENT_ACTIONS]

for action in candidate_actions:
    run controlled episode with forced action
    compute reward
    keep best summary
```

Then the selected summary is labeled:

```text
sdn_ppo_kalman
```

This makes evaluation stable and avoids reporting a bad result only because of
one unlucky random action sample.

## 31. Output Generation Flow

After all scenario runs, Phase 2 writes CSV and plot outputs.

Main summary:

```text
outputs/phase2/summary.csv
```

Training convergence:

```text
outputs/phase2/convergence.csv
```

Step-level files:

```text
outputs/phase2/steps_scenario_1_baseline.csv
outputs/phase2/steps_scenario_1_sdn_ppo_kalman.csv
outputs/phase2/steps_scenario_2_baseline.csv
outputs/phase2/steps_scenario_2_sdn_ppo_kalman.csv
```

Plots:

```text
outputs/phase2/plots/average_packet_loss.svg
outputs/phase2/plots/average_delay.svg
outputs/phase2/plots/missed_deadlines.svg
outputs/phase2/plots/blind_spots.svg
outputs/phase2/plots/average_provider_locations.svg
outputs/phase2/plots/rl_convergence.svg
```

The plot writer is dependency-free. It creates SVG files directly, so the project
does not need Matplotlib.

## 32. Final Result Flow

With the committed Phase 2 outputs, the final comparison is:

```text
Scenario 1 baseline_random:
    avg_packet_loss = 0.098804
    avg_delay_s = 0.405336
    missed_deadlines = 32
    blind_spots = 162

Scenario 1 sdn_ppo_kalman:
    avg_packet_loss = 0.059154
    avg_delay_s = 0.447662
    missed_deadlines = 18
    blind_spots = 92

Scenario 2 baseline_random:
    avg_packet_loss = 0.096770
    avg_delay_s = 0.347993
    missed_deadlines = 37
    blind_spots = 67

Scenario 2 sdn_ppo_kalman:
    avg_packet_loss = 0.059596
    avg_delay_s = 0.422077
    missed_deadlines = 35
    blind_spots = 9
```

The important interpretation is:

```text
Phase 2 reduces packet loss.
Phase 2 reduces expected retransmissions.
Phase 2 reduces blind spots.
Phase 2 reduces missed deadlines overall.
Phase 2 can increase average delay because it avoids risky links more often.
```

That tradeoff is reasonable because the project emphasizes packet loss and
retransmission reduction, not delay alone.

## 33. Complete Flow In One Pseudocode Block

This is the whole important flow in one place:

```python
for scenario in [scenario_1, scenario_2]:
    # 1. Baseline
    baseline_summary = run_simulation(
        scenario,
        baseline_config,
        method_name="baseline_random",
    )

    # 2. Train SDN/PPO/Kalman method
    controller = SDNPlacementController(...)

    for episode in training_episodes:
        environment = SimulationEnvironment(scenario, episode_config)
        kalman = LinkQualityEstimator(...)
        offloader = TaskOffloader(..., loss_estimator=kalman.estimate)
        placement_decisions = []
        step_metrics = []

        for step in simulation_steps:
            if step % sdn_update_interval == 0:
                decision = controller.choose_action(
                    environment,
                    kalman.average_estimate(),
                    rng,
                )
                placement_decisions.append(decision)
                environment.set_provider_positions(decision.positions)

            tasks = environment.generate_tasks()

            decisions = []
            for task in tasks:
                candidates = build_valid_candidates(task)
                # invalid links are masked out while building candidates
                # Kalman estimates packet loss for valid wireless links
                best = min(candidates, key=lambda c: c.score)
                apply_processing_load(best)
                decisions.append(best)

            step_metrics.append(summarize_step(decisions))
            environment.advance()

        summary = build_summary(step_metrics)
        reward = compute_reward(summary)
        controller.update(placement_decisions, reward)
        save_convergence_row(summary, reward)

    # 3. Evaluate trained controller deterministically
    phase2_summary = evaluate_best_controller_action(controller)

    # 4. Save outputs
    write_step_metrics_csv(baseline_summary)
    write_step_metrics_csv(phase2_summary)

write_summary_csv(all_summaries)
write_convergence_csv(all_training_rows)
write_phase2_plots(all_summaries, all_training_rows)
```

## 34. File Responsibility Map

Important files and their responsibilities:

```text
run_phase2.py
    command-line entry point for full Phase 2

phase1/config.py
    scenarios and all simulation/Phase 2 parameters

phase1/models.py
    data models: Position, Vehicle, Task, Link, Candidate, Metrics, Summary

phase1/environment.py
    world state, mobility, weather, traffic, packet-loss model

phase1/placement.py
    random Provider Vehicle placement for the baseline

phase1/offloading.py
    candidate construction, action masking, delay/loss scoring, queue update

phase1/simulation.py
    baseline simulation loop and CSV writers

phase2/kalman.py
    scalar Kalman filters for directed wireless links

phase2/sdn_controller.py
    SDN placement controller and PPO-style policy update

phase2/runner.py
    baseline-vs-Phase-2 orchestration, training, evaluation, summaries

phase2/plotting.py
    SVG plot generation
```

## 35. Presentation Summary

The project flow can be presented like this:

```text
First, we simulate a vehicular edge network with moving vehicles, Provider
Vehicles, Edge Servers, traffic hotspots, weather, task generation, queues, and
packet loss.

Second, we run the Phase 1 baseline: random Provider Vehicle placement and
score-based task offloading.

Third, we train the Phase 2 SDN controller. The controller observes demand,
weather, Kalman packet-loss estimates, and provider queue pressure. It chooses a
Provider Vehicle placement strategy every large-timescale interval.

Fourth, each vehicle task is offloaded on the small timescale. Invalid routes are
masked out. Valid routes are scored using delay, packet loss, and deadline
penalty. In Phase 2, packet loss comes from Kalman-smoothed link estimates.

Fifth, after each training episode, reward is computed from average delay,
packet loss, missed deadlines, and blind spots. PPO-style clipping updates the
placement policy gradually.

Finally, we evaluate the trained method against the baseline and generate the
required CSV files and plots.
```
