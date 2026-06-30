# Prerequisites From Scratch

This file explains the technical words needed to understand Phase 1 of the
project. It starts from the basic idea and moves toward the exact terms used in
the implementation.

## 1. What Problem Are We Solving?

In a vehicular network, cars can create computational tasks. For example, a car
might need to process sensor data, detect objects, update a map, or run a small
AI model.

The car has three possible choices:

1. Process the task on itself.
2. Send the task to a nearby provider vehicle.
3. Send the task to a fixed edge server, directly or through a provider vehicle.

The goal is to choose a destination and a route that reduce delay and packet
loss.

## 2. Vehicle

A vehicle is a normal moving car in the simulation.

In this project, a vehicle:

- has a two-dimensional position `(x, y)`
- moves every simulation step
- may generate computational tasks
- can process tasks locally, but with limited compute power
- can send tasks to provider vehicles or edge servers if they are in range

In the code, normal vehicles are represented by the `Vehicle` model.

## 3. Provider Vehicle

A provider vehicle is a special vehicle that helps the network.

It can act as:

- a mobile edge server: it processes tasks for other vehicles
- a relay: it forwards tasks from a vehicle to a fixed edge server

Provider vehicles are important because they can move close to high-demand
areas. In Phase 1, their placement is random. In Phase 2, the SDN controller can
learn better positions for them.

In the code, provider vehicles are represented by the `ProviderVehicle` model.

## 4. Edge Server

An edge server is a fixed computing server near the road network.

It usually has more compute power than a normal vehicle or provider vehicle.
Because it is fixed, it does not move, but a vehicle must still be close enough
to communicate with it directly, or it must reach it through a relay.

In the code, edge servers are represented by the `EdgeServer` model.

## 5. Edge Computing

Edge computing means processing data near the user instead of sending everything
to a far cloud server.

For vehicles, this is useful because:

- decisions must often be made quickly
- wireless communication can be unstable
- sending all data to a remote cloud may create high delay

In this project, provider vehicles and fixed edge servers are the edge resources.

## 6. Task

A task is a unit of computation created by a vehicle.

Each task has:

- `data_size_mbits`: how much data must be transmitted
- `compute_cycles_g`: how much CPU work is needed
- `deadline_s`: maximum acceptable completion time

If a task finishes after its deadline, we count it as a missed deadline.

In the code, tasks are represented by the `Task` model.

## 7. Task Offloading

Task offloading means sending a task from the source vehicle to another node for
processing.

Example:

- local processing: vehicle processes its own task
- provider offloading: vehicle sends the task to a provider vehicle
- edge offloading: vehicle sends the task to an edge server
- relay offloading: vehicle sends the task to a provider vehicle, then the
  provider forwards it to an edge server

The offloading algorithm must answer two questions:

1. Where should the task be processed?
2. Which route should the task use?

In Phase 1, we use a simple score-based baseline instead of reinforcement
learning.

## 8. Route

A route is the path used to transmit a task.

The implemented routes are:

- `local`: no wireless route; the vehicle processes the task itself
- `vehicle_to_provider`: vehicle sends directly to a provider vehicle
- `vehicle_to_edge`: vehicle sends directly to a fixed edge server
- `vehicle_provider_edge`: vehicle sends to provider, then provider sends to edge

Each wireless hop can add delay and packet-loss risk.

## 9. Wireless Link

A wireless link is one communication connection between two nodes.

Examples:

- vehicle to provider
- vehicle to edge server
- provider to edge server

A link is valid only if the target is within radio range. If the target is too
far away, the link is invalid and cannot be used.

In the code, valid wireless hops are represented by the `Link` model.

## 10. Radio Range

Radio range is the maximum distance at which two nodes can communicate.

If the distance between two nodes is larger than the radio range, the link is
not allowed.

This is the main idea behind action masking in Phase 1: out-of-range choices are
removed before the algorithm chooses an action.

## 11. Packet Loss

Packet loss means transmitted data does not successfully arrive.

In real vehicular networks, packet loss can happen because of:

- long distance between sender and receiver
- bad weather
- wireless interference
- high traffic density
- obstacles and movement

In this simulator, packet loss is estimated from:

- distance between nodes
- local traffic density
- current weather

The result is a probability between `0` and `1`.

Example:

- `0.05` means about 5 percent packet-loss probability
- `0.30` means about 30 percent packet-loss probability

## 12. Retransmission

Retransmission means sending the same packet again after failure.

Higher packet loss means more expected retransmissions. More retransmissions
increase delay because the same data may need to be sent multiple times.

Phase 1 does not simulate every individual packet. Instead, it estimates the
expected number of transmission attempts using:

```text
expected_attempts = 1 / (1 - packet_loss)
```

Then transmission delay is multiplied by this value.

## 13. Delay

Delay is the time needed to finish a task.

For local processing:

```text
delay = queue_waiting_time + processing_time
```

For offloading:

```text
delay = transmission_delay + queue_waiting_time + processing_time
```

The simulator reports average system delay across generated tasks.

## 14. Deadline

A deadline is the latest acceptable completion time for a task.

If:

```text
delay > deadline
```

then the task missed its deadline.

The simulator counts missed deadlines because real-time systems care not only
about average delay, but also about whether tasks finish on time.

## 15. Queue

A queue represents work already waiting at a node.

If many tasks are sent to the same provider or edge server, its queue grows. A
new task must wait for previous work before it can be processed.

The simulator stores queue time in seconds. Every simulation step reduces the
queue because time passes.

## 16. Blind Spot

In this project, a blind spot means a vehicle cannot reach any remote processing
node.

So, if a vehicle has no valid provider or edge link, it is in a blind spot for
remote offloading. It can still process locally, but it has no communication
help from the edge network.

The simulator counts blind-spot occurrences.

## 17. Traffic Density

Traffic density means how crowded an area is.

In the simulator, some map regions are treated as hotspots. A position near a
hotspot has higher demand. We also count nearby vehicles.

Higher traffic density increases packet-loss probability.

## 18. Weather

Weather affects wireless communication.

The simulator uses four simple weather states:

- clear
- rain
- fog
- storm

Bad weather adds a packet-loss penalty.

## 19. SDN

SDN means Software Defined Network.

The main idea is to separate:

- the controller: makes global network decisions
- the forwarding/data layer: executes communication decisions

In the full project, the SDN controller should place provider vehicles using a
large-timescale policy. In Phase 1, we only build the simulation base and use
random provider placement.

## 20. Two-Timescale Framework

Two-timescale means the system makes two kinds of decisions at different speeds.

Large timescale:

- happens less frequently
- SDN controller decides provider vehicle placement

Small timescale:

- happens frequently
- each vehicle decides task offloading and routing

Phase 1 focuses on the environment, random large-timescale placement, and simple
small-timescale offloading.

## 21. Kalman Filter

A Kalman filter is an algorithm for estimating a hidden value from noisy
measurements.

In this project idea, vehicles would use it to estimate link quality and predict
packet loss.

Phase 1 does not implement a Kalman filter yet. Instead, the simulator directly
computes packet-loss estimates from distance, traffic, and weather. This keeps
Phase 1 simple while leaving a clear place for Kalman-based estimation in Phase
2.

## 22. Link Quality Estimation

Link Quality Estimation, or LQE, means estimating how good or bad a wireless
link is.

Packet-loss probability is one form of link-quality information.

Good link:

- low packet loss
- low delay
- fewer retransmissions

Bad link:

- high packet loss
- high delay
- more retransmissions

## 23. Reinforcement Learning

Reinforcement learning is a machine learning method where an agent learns by
trying actions and receiving rewards.

The agent observes a state, chooses an action, gets a reward, and slowly learns
which actions are better.

Phase 2 will use reinforcement learning. Phase 1 does not train a model.

## 24. PPO

PPO means Proximal Policy Optimization.

It is a common reinforcement learning algorithm. In the full project, PPO is
intended for the SDN controller so it can learn provider vehicle coordinates.

Phase 1 uses random placement as the baseline that PPO can later beat.

## 25. CTDE

CTDE means Centralized Training, Decentralized Execution.

It means:

- training can use global information
- execution should work locally at each vehicle

In the full project, the SDN controller can help train the policy, but vehicles
should later make offloading decisions in a decentralized way.

Phase 1 does not train a CTDE model. It creates the baseline simulation needed
before that step.

## 26. Action Space

The action space is the set of all actions an algorithm can choose from.

Here, an action means:

```text
choose destination + choose route
```

Examples:

- process locally
- send to provider 1
- send directly to edge server 0
- send through provider 2 to edge server 1

## 27. Action Masking

Action masking means removing impossible actions before choosing.

Example:

If provider 1 is outside radio range, then `send to provider 1` is invalid. The
offloading algorithm should not choose it.

In the code, invalid wireless links return `None`. Candidates using those links
are not added to the candidate list.

## 28. Baseline Method

A baseline is a simple method used for comparison.

A good baseline should be:

- easy to understand
- reproducible
- complete enough to solve the problem
- weaker than the final intelligent method, but not meaningless

Phase 1 is a baseline with random provider placement and score-based offloading.

## 29. Simulation Step

A simulation step is one tick of simulated time.

At each step:

1. vehicles may generate tasks
2. the offloader decides where each task goes
3. metrics are saved
4. vehicles move
5. queues decrease as time passes
6. weather may change

## 30. Metrics

Metrics are the values we measure to evaluate the system.

Phase 1 produces:

- average packet-loss ratio
- average delay
- missed deadlines
- blind-spot occurrences
- average provider vehicle location
- route and destination counts

These are saved as CSV files so Phase 2 can plot them.

## 31. CSV

CSV means Comma-Separated Values.

It is a simple table format that can be opened by Excel, Python, pandas,
MATLAB, or plotting tools.

The simulator writes:

- `summary.csv`: one row per scenario
- `steps_scenario_1.csv`: time-series metrics for scenario 1
- `steps_scenario_2.csv`: time-series metrics for scenario 2
