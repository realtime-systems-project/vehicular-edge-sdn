"""Configuration objects for the vehicular edge simulator.

All values use simple SI-like units:
- positions and radio ranges are meters
- data sizes are megabits
- bandwidth is megabits per second
- compute demand is giga-cycles
- compute speed is giga-cycles per second
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ScenarioConfig:
    """Numbers that define one required experiment scenario.

    The project asks for exactly two scenarios. We keep only the counts here so
    the same simulator and offloading logic can run both cases unchanged.
    """

    name: str
    vehicle_count: int
    provider_count: int
    edge_count: int


@dataclass(frozen=True)
class SimulationConfig:
    """Physical, network, and workload parameters shared by all scenarios.

    Phase 1 is a baseline simulator, so these values are intentionally simple
    constants instead of learned parameters. Phase 2 can tune or replace them
    when PPO/Kalman components are added.
    """

    area_width_m: float = 1000.0
    area_height_m: float = 1000.0
    steps: int = 120
    time_step_s: float = 1.0
    seed: int = 7

    task_probability_per_vehicle: float = 0.35
    min_task_size_mbits: float = 1.0
    max_task_size_mbits: float = 8.0
    min_task_cycles_g: float = 0.3
    max_task_cycles_g: float = 3.5
    min_deadline_s: float = 0.4
    max_deadline_s: float = 2.5

    vehicle_compute_gps: float = 3.0
    provider_compute_gps: float = 18.0
    edge_compute_gps: float = 35.0

    vehicle_to_provider_range_m: float = 300.0
    vehicle_to_edge_range_m: float = 330.0
    provider_to_edge_range_m: float = 650.0

    vehicle_to_provider_bandwidth_mbps: float = 28.0
    vehicle_to_edge_bandwidth_mbps: float = 22.0
    provider_to_edge_bandwidth_mbps: float = 45.0

    loss_weight_s: float = 1.1
    deadline_weight_s: float = 3.0

    vehicle_min_speed_mps: float = 4.0
    vehicle_max_speed_mps: float = 17.0
    direction_noise_rad: float = 0.35


@dataclass(frozen=True)
class Phase2Config:
    """Learning and plotting parameters used by the Phase 2 controller.

    These values keep the reinforcement-learning part small enough to present
    while still matching the project idea: the SDN controller acts on a larger
    timescale, uses traffic/weather/link-quality information, and is compared
    against the random-placement baseline.
    """

    training_episodes: int = 24
    evaluation_steps: int = 120
    sdn_update_interval_steps: int = 10
    provider_move_fraction: float = 0.75

    ppo_learning_rate: float = 0.18
    ppo_clip_epsilon: float = 0.20
    entropy_bonus: float = 0.015

    reward_delay_weight: float = 1.0
    reward_loss_weight: float = 3.4
    reward_deadline_weight: float = 1.0
    reward_blind_spot_weight: float = 1.4

    kalman_process_noise: float = 0.004
    kalman_measurement_noise: float = 0.035
    kalman_measurement_jitter: float = 0.025

    phase2_loss_weight_s: float = 2.4
    phase2_deadline_weight_s: float = 7.0


SCENARIOS: Dict[int, ScenarioConfig] = {
    # Scenario 1 from the project description: 20 vehicles, 3 providers, 2 edges.
    1: ScenarioConfig(
        name="scenario_1",
        vehicle_count=20,
        provider_count=3,
        edge_count=2,
    ),
    # Scenario 2 from the project description: 50 vehicles, 6 providers, 4 edges.
    2: ScenarioConfig(
        name="scenario_2",
        vehicle_count=50,
        provider_count=6,
        edge_count=4,
    ),
}
