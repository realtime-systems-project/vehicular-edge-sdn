# Project 11

## Designing an SDN-Based Framework for Provider Vehicle Deployment and Task Offloading

**Teaching Assistant: Mr. Abbas Shabrang**

In vehicular edge computing networks, provider vehicles are used as mobile edge servers or communication relays to assist in processing vehicle tasks.

One of the fundamental challenges in these networks is the highly dynamic environment and the high probability of packet loss during task transmission. In addition, optimal placement of provider vehicles creates a significant challenge for continuous service delivery. In this project, we aim to develop a two-timescale framework using a Software Defined Network (SDN) controller. At the large timescale, the SDN controller places provider vehicles in a two-dimensional environment based on weather conditions, traffic distribution, and packet-loss maps. At the small timescale, vehicles use a Kalman filter to estimate link quality and predict packet loss, then decide to which node (the vehicle itself, a provider vehicle, or a fixed edge server) each task should be sent and through which route, so that retransmissions are minimized. The main objective of the system is the joint reduction of delay and packet loss.

## Proposed Algorithm

To solve this problem, a combination of the CTDE (Centralized Training, Decentralized Execution) paradigm and deep reinforcement learning algorithms is used. The SDN controller employs PPO to continuously control the coordinates of provider vehicles. Its state space includes traffic density, weather conditions, and Kalman filter outputs. The SDN reward function is designed to minimize packet loss by balancing capacity and demand. At the same time, vehicles use the model trained by the SDN controller in a decentralized manner for task offloading. Each vehicle's state includes task queue length, task features, and Kalman prediction outputs. The action space consists of jointly selecting the processing destination and transmission route. Invalid options (such as out-of-range nodes) are filtered using action masking.

## Expected Plots

The following plots should be generated under two scenarios:

Scenario 1 includes 20 vehicles, 3 provider vehicles, and 2 edge servers. Scenario 2 includes 50 vehicles, 6 provider vehicles, and 4 edge servers.

- Average packet-loss ratio across the network
- Average system delay
- Number of missed deadlines
- Number of blind-spot occurrences
- Average location of provider vehicles
- Convergence curves of reinforcement learning algorithms

Phase 1: Generate the simulation environment and defined parameters, implement a random placement method for provider vehicles, and implement a task-offloading algorithm.

Phase 2: Full implementation of the project along with final plots and comparison of the obtained results with the baseline method.
