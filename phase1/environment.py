"""Simulation environment for Phase 1."""

from __future__ import annotations

from math import cos, exp, pi, sin
from random import Random
from typing import Dict, Iterable, List, Optional, Tuple

from .config import ScenarioConfig, SimulationConfig
from .models import EdgeServer, Position, ProviderVehicle, Task, Vehicle
from .placement import random_provider_placement


WEATHER_LOSS_PENALTY: Dict[str, float] = {
    "clear": 0.00,
    "rain": 0.09,
    "fog": 0.13,
    "storm": 0.22,
}


class SimulationEnvironment:
    """Holds mutable world state and computes traffic, weather, and link loss.

    This class is the "world" of Phase 1. It owns node positions, mobility,
    task generation, weather changes, and the packet-loss map used by the
    offloading algorithm.
    """

    def __init__(self, scenario: ScenarioConfig, config: SimulationConfig):
        self.scenario = scenario
        self.config = config
        self.rng = Random(config.seed)
        self.step_index = 0
        self.next_task_id = 0
        self.weather = "clear"

        self.vehicles = self._create_vehicles()
        self.providers = random_provider_placement(
            scenario.provider_count,
            config.provider_compute_gps,
            config,
            self.rng,
        )
        self.edge_servers = self._create_edge_servers()
        self.hotspots = self._create_hotspots()

    def advance(self) -> None:
        """Move vehicles, decay queues, and occasionally update weather."""

        self.step_index += 1
        self._update_weather()
        self._move_vehicles()
        self._decay_queues(self.vehicles)
        self._decay_queues(self.providers)
        self._decay_queues(self.edge_servers)

    def generate_tasks(self) -> List[Task]:
        """Generate independent vehicle tasks for the current step."""

        tasks: List[Task] = []
        for vehicle in self.vehicles:
            if self.rng.random() > self.config.task_probability_per_vehicle:
                continue
            task = Task(
                task_id=self.next_task_id,
                vehicle_id=vehicle.node_id,
                created_at_step=self.step_index,
                data_size_mbits=self.rng.uniform(
                    self.config.min_task_size_mbits,
                    self.config.max_task_size_mbits,
                ),
                compute_cycles_g=self.rng.uniform(
                    self.config.min_task_cycles_g,
                    self.config.max_task_cycles_g,
                ),
                deadline_s=self.rng.uniform(
                    self.config.min_deadline_s,
                    self.config.max_deadline_s,
                ),
            )
            self.next_task_id += 1
            tasks.append(task)
        return tasks

    def provider_average_position(self) -> Position:
        """Return the average provider location required by the expected plots."""

        if not self.providers:
            return Position(0.0, 0.0)
        return Position(
            x=sum(provider.position.x for provider in self.providers) / len(self.providers),
            y=sum(provider.position.y for provider in self.providers) / len(self.providers),
        )

    def traffic_density_at(self, position: Position) -> float:
        """Estimate normalized local demand from hotspots and nearby vehicles."""

        hotspot_signal = 0.0
        for hotspot, weight in self.hotspots:
            distance = position.distance_to(hotspot)
            hotspot_signal += weight * exp(-(distance * distance) / (2.0 * 220.0 * 220.0))

        nearby_count = sum(
            1
            for vehicle in self.vehicles
            if vehicle.position.distance_to(position) <= 150.0
        )
        local_vehicle_density = nearby_count / max(1, len(self.vehicles))
        return self._clamp(0.08 + 0.55 * hotspot_signal + 0.65 * local_vehicle_density)

    def packet_loss_probability(
        self,
        source: Position,
        target: Position,
        radio_range_m: float,
    ) -> Optional[float]:
        """Return packet-loss probability, or None if the link is out of range."""

        distance = source.distance_to(target)
        if distance > radio_range_m:
            return None

        distance_ratio = distance / radio_range_m
        traffic = (self.traffic_density_at(source) + self.traffic_density_at(target)) / 2.0
        loss = (
            0.02
            + 0.28 * distance_ratio * distance_ratio
            + 0.18 * traffic
            + WEATHER_LOSS_PENALTY[self.weather]
        )
        return self._clamp(loss, low=0.01, high=0.85)

    def get_vehicle(self, vehicle_id: int) -> Vehicle:
        return self.vehicles[vehicle_id]

    def get_provider(self, provider_id: int) -> ProviderVehicle:
        return self.providers[provider_id]

    def get_edge(self, edge_id: int) -> EdgeServer:
        return self.edge_servers[edge_id]

    def _create_vehicles(self) -> List[Vehicle]:
        vehicles: List[Vehicle] = []
        for index in range(self.scenario.vehicle_count):
            vehicles.append(
                Vehicle(
                    node_id=index,
                    position=Position(
                        x=self.rng.uniform(0.0, self.config.area_width_m),
                        y=self.rng.uniform(0.0, self.config.area_height_m),
                    ),
                    compute_gps=self.config.vehicle_compute_gps,
                    speed_mps=self.rng.uniform(
                        self.config.vehicle_min_speed_mps,
                        self.config.vehicle_max_speed_mps,
                    ),
                    direction_rad=self.rng.uniform(0.0, 2.0 * pi),
                )
            )
        return vehicles

    def _create_edge_servers(self) -> List[EdgeServer]:
        """Place fixed edge servers along opposite sides of the map."""

        servers: List[EdgeServer] = []
        for index in range(self.scenario.edge_count):
            x = (index + 1) * self.config.area_width_m / (self.scenario.edge_count + 1)
            y = 0.08 * self.config.area_height_m
            if index % 2 == 1:
                y = 0.92 * self.config.area_height_m
            servers.append(
                EdgeServer(
                    node_id=index,
                    position=Position(x=x, y=y),
                    compute_gps=self.config.edge_compute_gps,
                )
            )
        return servers

    def _create_hotspots(self) -> List[Tuple[Position, float]]:
        """Create simple traffic hotspots used to vary local packet loss."""

        return [
            (Position(0.28 * self.config.area_width_m, 0.42 * self.config.area_height_m), 0.65),
            (Position(0.72 * self.config.area_width_m, 0.62 * self.config.area_height_m), 0.55),
        ]

    def _update_weather(self) -> None:
        """Update weather every 20 steps using fixed probabilities."""

        if self.step_index % 20 != 0:
            return
        roll = self.rng.random()
        if roll < 0.55:
            self.weather = "clear"
        elif roll < 0.78:
            self.weather = "rain"
        elif roll < 0.93:
            self.weather = "fog"
        else:
            self.weather = "storm"

    def _move_vehicles(self) -> None:
        """Move vehicles with mild random direction changes and boundary bounce."""

        for vehicle in self.vehicles:
            vehicle.direction_rad += self.rng.uniform(
                -self.config.direction_noise_rad,
                self.config.direction_noise_rad,
            )
            dx = cos(vehicle.direction_rad) * vehicle.speed_mps * self.config.time_step_s
            dy = sin(vehicle.direction_rad) * vehicle.speed_mps * self.config.time_step_s
            vehicle.position.x += dx
            vehicle.position.y += dy

            if vehicle.position.x < 0.0 or vehicle.position.x > self.config.area_width_m:
                vehicle.direction_rad = pi - vehicle.direction_rad
                vehicle.position.x = self._clamp(
                    vehicle.position.x,
                    low=0.0,
                    high=self.config.area_width_m,
                )
            if vehicle.position.y < 0.0 or vehicle.position.y > self.config.area_height_m:
                vehicle.direction_rad = -vehicle.direction_rad
                vehicle.position.y = self._clamp(
                    vehicle.position.y,
                    low=0.0,
                    high=self.config.area_height_m,
                )

    def _decay_queues(self, nodes: Iterable[object]) -> None:
        """Reduce each node's queued processing time as simulated time passes."""

        for node in nodes:
            node.queue_s = max(0.0, node.queue_s - self.config.time_step_s)

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))
