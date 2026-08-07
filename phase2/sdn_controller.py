"""SDN provider-placement controller for Phase 2.

The full project asks the SDN controller to place provider vehicles on a larger
timescale using traffic, weather, and Kalman link-quality information. To keep
the implementation readable and dependency-free, this module uses a compact
PPO-style policy over four placement strategies. Each strategy still outputs
continuous provider coordinates, while PPO updates the probability of choosing
each strategy from episode rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from random import Random
from typing import Dict, List, Sequence, Tuple

from phase1.config import Phase2Config, SimulationConfig
from phase1.environment import WEATHER_LOSS_PENALTY, SimulationEnvironment
from phase1.models import Position


PLACEMENT_ACTIONS: Tuple[str, ...] = (
    "demand_center",
    "coverage_grid",
    "edge_bridge",
    "loss_aware",
    "balanced_grid",
    "capacity_demand",
)


@dataclass
class PlacementDecision:
    """One large-timescale SDN action and the probability used to sample it."""

    action_name: str
    probability: float
    state: Dict[str, float]
    positions: List[Position]


class SDNPlacementController:
    """Small PPO-style controller that chooses provider placement strategies."""

    def __init__(self, sim_config: SimulationConfig, phase2_config: Phase2Config):
        """Initialize policy logits and controller hyperparameters."""

        self.sim_config = sim_config
        self.phase2_config = phase2_config
        self.logits: Dict[str, float] = {action: 0.0 for action in PLACEMENT_ACTIONS}
        self.reward_baseline = 0.0
        self.reward_count = 0
        self.best_observed_action = "balanced_grid"
        self.best_observed_reward = float("-inf")

    def choose_action(
        self,
        environment: SimulationEnvironment,
        average_kalman_loss: float,
        rng: Random,
    ) -> PlacementDecision:
        """Sample a placement action and return clipped target coordinates."""

        state = self._state(environment, average_kalman_loss)
        probabilities = self._policy()
        action_name = self._sample_action(probabilities, rng)
        raw_positions = self._positions_for_action(action_name, state, environment)
        positions = self._move_toward_targets(environment, raw_positions)
        return PlacementDecision(
            action_name=action_name,
            probability=probabilities[action_name],
            state=state,
            positions=positions,
        )

    def update(self, decisions: Sequence[PlacementDecision], reward: float) -> float:
        """Apply a clipped PPO-style policy update and return the advantage."""

        if decisions and reward > self.best_observed_reward:
            self.best_observed_reward = reward
            self.best_observed_action = _most_common_action(decisions)

        self.reward_count += 1
        self.reward_baseline += (reward - self.reward_baseline) / self.reward_count
        advantage = reward - self.reward_baseline

        old_probabilities = self._policy()
        for decision in decisions:
            old_probability = max(1e-6, decision.probability)
            current_probability = max(1e-6, old_probabilities[decision.action_name])
            ratio = current_probability / old_probability
            clipped_ratio = self._clamp(
                ratio,
                low=1.0 - self.phase2_config.ppo_clip_epsilon,
                high=1.0 + self.phase2_config.ppo_clip_epsilon,
            )
            direction = 1.0 if advantage >= 0.0 else -1.0
            update_size = (
                self.phase2_config.ppo_learning_rate
                * direction
                * min(abs(ratio * advantage), abs(clipped_ratio * advantage))
            )
            self.logits[decision.action_name] += update_size

        self._apply_entropy_bonus()
        self._center_logits()
        return advantage

    def best_action_name(self) -> str:
        """Return the best training-observed strategy for deterministic evaluation."""

        return self.best_observed_action

    def force_action(
        self,
        action_name: str,
        environment: SimulationEnvironment,
        average_kalman_loss: float,
    ) -> List[Position]:
        """Return target positions for evaluation without random sampling."""

        state = self._state(environment, average_kalman_loss)
        return self._move_toward_targets(
            environment,
            self._positions_for_action(action_name, state, environment),
        )

    def _state(
        self,
        environment: SimulationEnvironment,
        average_kalman_loss: float,
    ) -> Dict[str, float]:
        """Build the SDN state from demand, weather, queues, and Kalman output."""

        demand = environment.demand_center()
        provider_queue = sum(provider.queue_s for provider in environment.providers)
        provider_queue /= max(1, len(environment.providers))
        return {
            "demand_x": demand.x,
            "demand_y": demand.y,
            "weather_loss": WEATHER_LOSS_PENALTY[environment.weather],
            "average_kalman_loss": average_kalman_loss,
            "provider_queue": provider_queue,
        }

    def _positions_for_action(
        self,
        action_name: str,
        state: Dict[str, float],
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Generate continuous provider coordinates for one strategy."""

        if action_name == "coverage_grid":
            return self._coverage_grid_positions(environment)
        if action_name == "edge_bridge":
            return self._edge_bridge_positions(state, environment)
        if action_name == "loss_aware":
            return self._loss_aware_positions(state, environment)
        if action_name == "balanced_grid":
            return self._balanced_grid_positions(state, environment)
        if action_name == "capacity_demand":
            return self._capacity_demand_positions(environment)
        return self._demand_center_positions(state, environment)

    def _demand_center_positions(
        self,
        state: Dict[str, float],
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Place providers around the current demand center."""

        return self._ring_positions(
            center=Position(state["demand_x"], state["demand_y"]),
            radius=125.0,
            count=len(environment.providers),
        )

    def _coverage_grid_positions(
        self,
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Spread providers across the map to reduce blind spots."""

        count = len(environment.providers)
        positions: List[Position] = []
        for index in range(count):
            x_fraction = ((index % 3) + 1) / 4.0
            row_count = max(1, (count + 2) // 3)
            y_fraction = ((index // 3) + 1) / (row_count + 1)
            positions.append(
                Position(
                    x_fraction * self.sim_config.area_width_m,
                    y_fraction * self.sim_config.area_height_m,
                )
            )
        return positions

    def _edge_bridge_positions(
        self,
        state: Dict[str, float],
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Place providers between the demand center and fixed edge servers."""

        demand = Position(state["demand_x"], state["demand_y"])
        positions: List[Position] = []
        for index, _provider in enumerate(environment.providers):
            edge = environment.edge_servers[index % len(environment.edge_servers)]
            weight = 0.45 + 0.10 * (index % 3)
            positions.append(
                Position(
                    x=demand.x * (1.0 - weight) + edge.position.x * weight,
                    y=demand.y * (1.0 - weight) + edge.position.y * weight,
                )
            )
        return positions

    def _loss_aware_positions(
        self,
        state: Dict[str, float],
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Move providers closer to demand when weather or Kalman loss is high."""

        stress = self._clamp(
            state["weather_loss"] + state["average_kalman_loss"],
            low=0.0,
            high=0.8,
        )
        radius = 180.0 - 120.0 * stress
        return self._ring_positions(
            center=Position(state["demand_x"], state["demand_y"]),
            radius=max(60.0, radius),
            count=len(environment.providers),
        )

    def _balanced_grid_positions(
        self,
        state: Dict[str, float],
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Split providers between demand service and map-wide coverage.

        This action is important for the larger scenario: putting every provider
        near the demand center can reduce delay for some tasks but creates blind
        spots elsewhere. The balanced strategy keeps half the providers near
        demand and spreads the rest over the map.
        """

        count = len(environment.providers)
        demand_count = max(1, count // 2)
        demand_positions = self._ring_positions(
            center=Position(state["demand_x"], state["demand_y"]),
            radius=110.0,
            count=demand_count,
        )
        coverage_positions = self._coverage_grid_positions(environment)
        return demand_positions + coverage_positions[: count - demand_count]

    def _capacity_demand_positions(
        self,
        environment: SimulationEnvironment,
    ) -> List[Position]:
        """Place providers at weighted vehicle-demand clusters.

        This is the most direct implementation of the SDN reward idea from the
        project statement: providers should cover where vehicle demand actually
        exists, not only the global average demand center.
        """

        count = len(environment.providers)
        if count == 0:
            return []

        centers = self._coverage_grid_positions(environment)[:count]
        for _iteration in range(5):
            totals = [0.0 for _ in centers]
            xs = [0.0 for _ in centers]
            ys = [0.0 for _ in centers]
            for vehicle in environment.vehicles:
                best_index = min(
                    range(len(centers)),
                    key=lambda index: vehicle.position.distance_to(centers[index]),
                )
                weight = 0.35 + environment.traffic_density_at(vehicle.position)
                totals[best_index] += weight
                xs[best_index] += vehicle.position.x * weight
                ys[best_index] += vehicle.position.y * weight

            for index, total in enumerate(totals):
                if total > 0.0:
                    centers[index] = Position(xs[index] / total, ys[index] / total)

        return centers

    def _ring_positions(self, center: Position, radius: float, count: int) -> List[Position]:
        """Return evenly spaced positions around a center point."""

        if count <= 0:
            return []
        positions: List[Position] = []
        for index in range(count):
            angle_fraction = index / count
            if count == 1:
                angle_fraction = 0.0
            angle = 6.283185307179586 * angle_fraction
            positions.append(
                Position(
                    x=center.x + radius * self._cos(angle),
                    y=center.y + radius * self._sin(angle),
                )
            )
        return positions

    def _move_toward_targets(
        self,
        environment: SimulationEnvironment,
        targets: Sequence[Position],
    ) -> List[Position]:
        """Limit provider movement so placement is continuous, not teleporting."""

        positions: List[Position] = []
        fraction = self.phase2_config.provider_move_fraction
        for provider, target in zip(environment.providers, targets):
            positions.append(
                Position(
                    x=provider.position.x + fraction * (target.x - provider.position.x),
                    y=provider.position.y + fraction * (target.y - provider.position.y),
                )
            )
        return positions

    def _policy(self) -> Dict[str, float]:
        """Convert logits to a probability distribution with softmax."""

        max_logit = max(self.logits.values())
        exp_values = {
            action: exp(logit - max_logit) for action, logit in self.logits.items()
        }
        total = sum(exp_values.values())
        return {action: value / total for action, value in exp_values.items()}

    def _sample_action(self, probabilities: Dict[str, float], rng: Random) -> str:
        """Sample one placement strategy from the current policy."""

        threshold = rng.random()
        cumulative = 0.0
        for action_name, probability in probabilities.items():
            cumulative += probability
            if threshold <= cumulative:
                return action_name
        return PLACEMENT_ACTIONS[-1]

    def _apply_entropy_bonus(self) -> None:
        """Nudge logits toward exploration so training does not collapse early."""

        probabilities = self._policy()
        uniform = 1.0 / len(PLACEMENT_ACTIONS)
        for action_name, probability in probabilities.items():
            self.logits[action_name] += self.phase2_config.entropy_bonus * (
                uniform - probability
            )

    def _center_logits(self) -> None:
        """Keep logits numerically stable by removing their mean."""

        mean = sum(self.logits.values()) / len(self.logits)
        for action_name in self.logits:
            self.logits[action_name] -= mean

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        """Clamp a numeric value to a closed interval."""

        return max(low, min(high, value))

    @staticmethod
    def _sin(angle: float) -> float:
        """Small wrapper to keep imports explicit near the controller math."""

        from math import sin

        return sin(angle)

    @staticmethod
    def _cos(angle: float) -> float:
        """Small wrapper to keep imports explicit near the controller math."""

        from math import cos

        return cos(angle)


def _most_common_action(decisions: Sequence[PlacementDecision]) -> str:
    """Return the placement action sampled most often in one episode."""

    counts: Dict[str, int] = {}
    for decision in decisions:
        counts[decision.action_name] = counts.get(decision.action_name, 0) + 1
    return max(counts, key=counts.get)
