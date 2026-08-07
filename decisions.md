# Technical Decisions

This file explains the decisions behind the full Phase 2 implementation. It is
not a list of every line of code. It focuses on places where we actually had to
choose an algorithm, coefficient, model, or simplification.

## 1. Keeping Phase 1 As The Baseline

Decision:

```text
Keep Phase 1 random provider placement as the baseline.
```

Reason:

The project explicitly says Phase 2 should compare final results with the
baseline method. Phase 1 already gives us a clear baseline:

- random provider placement
- score-based task offloading
- same scenarios
- same metrics

So Phase 2 does not overwrite Phase 1. It runs beside it.

## 2. No Heavy External Libraries

Decision:

```text
Use only the Python standard library.
```

Reason:

The project should run easily on a clean machine. A full deep RL stack would
require packages like NumPy, PyTorch, or Stable-Baselines. That would make the
project harder to run and harder to explain.

Instead, Phase 2 implements a small PPO-style controller directly in Python.
This is simpler, but still follows the project structure:

- state
- action
- reward
- policy update
- convergence curve

## 3. PPO-Style Controller Instead Of A Neural PPO Model

Decision:

```text
Use PPO-style clipped policy updates over placement strategies.
```

Reason:

The project says the SDN controller should use PPO to control provider vehicle
coordinates. A full neural PPO implementation would be too large for this course
phase and would hide the idea behind many library details.

So we used a compact PPO-style policy:

- the SDN controller has several placement actions
- each action creates continuous provider coordinates
- the controller samples actions during training
- rewards update action probabilities
- the update uses PPO clipping

The implemented PPO-style ratio is:

```text
ratio = current_probability / old_probability
clipped_ratio = clip(ratio, 1 - epsilon, 1 + epsilon)
```

The clip value is:

```text
epsilon = 0.20
```

Reason for `0.20`:

This is the common PPO clipping value. It prevents the policy from changing too
aggressively after one episode.

## 4. Large-Timescale SDN Update Interval

Decision:

```text
Update provider placement every 10 simulation steps.
```

Reason:

The project describes a two-timescale framework:

- large timescale: SDN placement
- small timescale: task offloading

If provider placement changed every step, it would be too similar to the
small-timescale offloading decision. If it changed only once, it would not react
to mobility or weather.

So `10` steps is a middle choice:

- slower than task decisions
- frequent enough to react to the environment
- easy to explain

## 5. Provider Movement Fraction

Decision:

```text
provider_move_fraction = 0.75
```

Reason:

Provider vehicles should not instantly teleport to target coordinates. But if
movement is too slow, the controller cannot affect the simulation much.

So every SDN update moves each provider 75 percent of the way toward its target.
This models continuous control while keeping the implementation simple.

## 6. SDN State

Decision:

The SDN controller state includes:

- demand center
- weather packet-loss penalty
- average Kalman packet-loss estimate
- average provider queue

Reason:

This matches the project text:

- traffic distribution is represented by the demand center
- weather condition is represented by weather penalty
- packet-loss map/Kalman output is represented by average Kalman loss
- capacity-demand pressure is represented by provider queue

## 7. Provider Placement Actions

Decision:

Use six placement strategies:

- `demand_center`
- `coverage_grid`
- `edge_bridge`
- `loss_aware`
- `balanced_grid`
- `capacity_demand`

Reason:

The action space should be small enough to train without a heavy RL library, but
rich enough to represent different SDN placement behaviors.

`demand_center`
: Places providers near current demand.

`coverage_grid`
: Spreads providers across the map to reduce blind spots.

`edge_bridge`
: Places providers between demand and fixed edge servers.

`loss_aware`
: Moves providers closer to demand when weather or Kalman loss is high.

`balanced_grid`
: Splits providers between demand and coverage.

`capacity_demand`
: Uses weighted vehicle-demand clustering to place providers near actual demand
clusters.

The last action was added because the larger scenario can have multiple demand
regions. A single demand center can over-cluster providers and create blind
spots.

## 8. Kalman Filter Model

Decision:

```text
Use one scalar Kalman filter per directed wireless link.
```

Reason:

The hidden state is packet-loss probability. That is a single number, so a
scalar Kalman filter is enough.

Each filter estimates:

```text
current packet-loss probability of one link
```

Parameters:

```text
process_noise = 0.004
measurement_noise = 0.035
measurement_jitter = 0.025
```

Reasoning:

- process noise is small because link quality changes gradually
- measurement noise is larger because wireless measurements are noisy
- jitter simulates imperfect packet-loss observations

## 9. Packet-Loss Formula

Decision:

Use:

```text
loss = 0.02 + 0.28 * distance_ratio^2 + 0.18 * traffic + weather_penalty
```

Reason:

Packet loss should increase with:

- distance
- traffic
- bad weather

The squared distance term makes links much worse near the edge of radio range,
which is realistic for wireless communication.

Loss is clamped to:

```text
0.01 <= loss <= 0.85
```

This avoids impossible values and avoids infinite retransmission estimates.

## 10. Delay Model

Decision:

Use:

```text
local delay = queue time + compute time
remote delay = transmission delay + destination queue time + compute time
```

Transmission delay:

```text
raw transmission delay = data size / bandwidth
expected attempts = 1 / (1 - packet loss)
effective transmission delay = raw delay * expected attempts
```

Reason:

Propagation delay is ignored because in a 1000m map it is around microseconds,
while transmission, queueing, processing, and retransmission delays are much
larger.

## 11. Phase 2 Offloading Score

Decision:

Phase 2 uses a higher packet-loss weight than Phase 1:

```text
phase2_loss_weight_s = 2.4
phase2_deadline_weight_s = 7.0
```

Reason:

The project's small-timescale goal is to minimize retransmissions. If the
offloader focuses too much on fast edge compute, it may choose remote routes with
high packet loss. The higher loss weight makes Phase 2 more conservative about
bad wireless links. The high deadline weight prevents the system from choosing
low-loss local processing when that misses a real-time deadline.

## 12. Reward Function

Decision:

The SDN reward is the negative weighted cost:

```text
reward = -(
    delay_weight * average_delay
  + loss_weight * average_packet_loss
  + deadline_weight * missed_deadlines / tasks
  + blind_spot_weight * blind_spots / tasks
)
```

Weights:

```text
delay_weight = 1.0
loss_weight = 3.4
deadline_weight = 1.0
blind_spot_weight = 1.4
```

Reason:

Packet loss receives a high weight because the project emphasizes packet loss
and retransmissions. Blind spots also receive a high weight because provider
deployment should improve service coverage. Missed deadlines are normalized by
task count so scenario 1 and scenario 2 are comparable.

## 13. Baseline Comparison

Decision:

Use the same scenario sizes and same evaluation length for baseline and Phase 2.

Reason:

The comparison should isolate the algorithmic change:

- baseline: random provider placement
- Phase 2: SDN/PPO/Kalman method

Both are run under the required scenarios.

## 14. Plot Format

Decision:

Generate plots as SVG files.

Reason:

SVG is text-based, easy to commit, and does not require Matplotlib. It also
works well in GitHub and browsers.

The generated plots are:

- average packet-loss ratio
- average delay
- missed deadlines
- blind spots
- average provider locations
- RL convergence curve

## 15. What We Did Not Add

Decision:

Do not add unrelated features beyond the project text.

Not added:

- cloud server model
- road-lane geometry
- real network packets
- external RL framework
- extra scenarios beyond the two required ones

Reason:

The project asks for a full implementation of the described SDN/offloading idea,
plots, and baseline comparison. Extra features would make the project harder to
explain without being required.
