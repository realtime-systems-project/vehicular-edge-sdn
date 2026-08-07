"""Task-offloading algorithms for baseline and Phase 2 runs.

The default `TaskOffloader` is the Phase 1 score-based baseline. Phase 2 reuses
the same action construction and masking, but injects a Kalman link estimator so
vehicles decide from predicted link quality instead of directly trusting the raw
packet-loss map.
"""

from __future__ import annotations

from math import prod
from random import Random
from typing import Callable, List, Optional, Sequence

from .config import SimulationConfig
from .environment import SimulationEnvironment
from .models import Link, OffloadCandidate, OffloadDecision, Position, Task

LossEstimator = Callable[[str, str, float, Random], float]


class TaskOffloader:
    """Choose the best valid destination and route for each task.

    The algorithm is a simple baseline:
    1. Build all valid actions: local processing, direct provider, direct edge,
       and edge through a provider relay.
    2. Mask invalid actions by radio range.
    3. Select the candidate with the lowest delay/loss/deadline score.
    """

    def __init__(
        self,
        config: SimulationConfig,
        loss_estimator: Optional[LossEstimator] = None,
    ):
        """Store scoring parameters and optional Kalman/LQE hook.

        When `loss_estimator` is absent, the offloader uses the environment's
        current packet-loss value directly. When present, the estimator receives
        the raw loss and returns a predicted loss for scoring and retransmission
        estimation.
        """

        self.config = config
        self.loss_estimator = loss_estimator

    def decide(self, task: Task, environment: SimulationEnvironment) -> OffloadDecision:
        """Return the best offloading decision for one task and update node queues."""

        candidates = self._build_candidates(task, environment)
        best = min(candidates, key=lambda candidate: candidate.score)
        self._apply_processing_load(best, environment)

        remote_candidates = [
            candidate for candidate in candidates if candidate.destination_type != "vehicle"
        ]
        return OffloadDecision(
            task=task,
            candidate=best,
            blind_spot=len(remote_candidates) == 0,
        )

    def _build_candidates(
        self,
        task: Task,
        environment: SimulationEnvironment,
    ) -> List[OffloadCandidate]:
        """Generate all currently valid actions after applying range masks."""

        vehicle = environment.get_vehicle(task.vehicle_id)
        candidates = [self._candidate_for_local(task, vehicle.node_id, vehicle.queue_s, vehicle.compute_gps)]

        for provider in environment.providers:
            link = self._make_link(
                source_id=f"vehicle:{vehicle.node_id}",
                target_id=f"provider:{provider.node_id}",
                source=vehicle.position,
                target=provider.position,
                radio_range_m=self.config.vehicle_to_provider_range_m,
                bandwidth_mbps=self.config.vehicle_to_provider_bandwidth_mbps,
                task=task,
                environment=environment,
            )
            if link is None:
                continue
            candidates.append(
                self._remote_candidate(
                    task=task,
                    destination_type="provider",
                    destination_id=provider.node_id,
                    route_name="vehicle_to_provider",
                    route=(f"vehicle:{vehicle.node_id}", f"provider:{provider.node_id}"),
                    links=(link,),
                    queue_s=provider.queue_s,
                    compute_gps=provider.compute_gps,
                )
            )

        for edge in environment.edge_servers:
            direct_link = self._make_link(
                source_id=f"vehicle:{vehicle.node_id}",
                target_id=f"edge:{edge.node_id}",
                source=vehicle.position,
                target=edge.position,
                radio_range_m=self.config.vehicle_to_edge_range_m,
                bandwidth_mbps=self.config.vehicle_to_edge_bandwidth_mbps,
                task=task,
                environment=environment,
            )
            if direct_link is not None:
                candidates.append(
                    self._remote_candidate(
                        task=task,
                        destination_type="edge",
                        destination_id=edge.node_id,
                        route_name="vehicle_to_edge",
                        route=(f"vehicle:{vehicle.node_id}", f"edge:{edge.node_id}"),
                        links=(direct_link,),
                        queue_s=edge.queue_s,
                        compute_gps=edge.compute_gps,
                    )
                )

            for provider in environment.providers:
                vehicle_provider = self._make_link(
                    source_id=f"vehicle:{vehicle.node_id}",
                    target_id=f"provider:{provider.node_id}",
                    source=vehicle.position,
                    target=provider.position,
                    radio_range_m=self.config.vehicle_to_provider_range_m,
                    bandwidth_mbps=self.config.vehicle_to_provider_bandwidth_mbps,
                    task=task,
                    environment=environment,
                )
                provider_edge = self._make_link(
                    source_id=f"provider:{provider.node_id}",
                    target_id=f"edge:{edge.node_id}",
                    source=provider.position,
                    target=edge.position,
                    radio_range_m=self.config.provider_to_edge_range_m,
                    bandwidth_mbps=self.config.provider_to_edge_bandwidth_mbps,
                    task=task,
                    environment=environment,
                )
                if vehicle_provider is None or provider_edge is None:
                    continue
                candidates.append(
                    self._remote_candidate(
                        task=task,
                        destination_type="edge",
                        destination_id=edge.node_id,
                        route_name="vehicle_provider_edge",
                        route=(
                            f"vehicle:{vehicle.node_id}",
                            f"provider:{provider.node_id}",
                            f"edge:{edge.node_id}",
                        ),
                        links=(vehicle_provider, provider_edge),
                        queue_s=edge.queue_s,
                        compute_gps=edge.compute_gps,
                    )
                )

        return candidates

    def _candidate_for_local(
        self,
        task: Task,
        vehicle_id: int,
        queue_s: float,
        compute_gps: float,
    ) -> OffloadCandidate:
        """Build the no-transmission candidate: process on the source vehicle."""

        processing_delay = queue_s + task.compute_cycles_g / compute_gps
        missed_deadline = processing_delay > task.deadline_s
        return OffloadCandidate(
            destination_type="vehicle",
            destination_id=vehicle_id,
            route_name="local",
            route=(f"vehicle:{vehicle_id}",),
            links=(),
            processing_delay_s=processing_delay,
            total_delay_s=processing_delay,
            packet_loss_probability=0.0,
            expected_retransmissions=0.0,
            missed_deadline=missed_deadline,
            score=self._score(processing_delay, 0.0, task.deadline_s),
        )

    def _remote_candidate(
        self,
        task: Task,
        destination_type: str,
        destination_id: int,
        route_name: str,
        route: Sequence[str],
        links: Sequence[Link],
        queue_s: float,
        compute_gps: float,
    ) -> OffloadCandidate:
        """Build a candidate that sends the task across one or more wireless hops."""

        processing_delay = queue_s + task.compute_cycles_g / compute_gps
        tx_delay = sum(link.tx_delay_s for link in links)
        loss_probability = 1.0 - prod(1.0 - link.loss_probability for link in links)
        expected_retransmissions = sum(link.expected_retransmissions for link in links)
        total_delay = tx_delay + processing_delay
        missed_deadline = total_delay > task.deadline_s
        return OffloadCandidate(
            destination_type=destination_type,
            destination_id=destination_id,
            route_name=route_name,
            route=tuple(route),
            links=tuple(links),
            processing_delay_s=processing_delay,
            total_delay_s=total_delay,
            packet_loss_probability=loss_probability,
            expected_retransmissions=expected_retransmissions,
            missed_deadline=missed_deadline,
            score=self._score(total_delay, loss_probability, task.deadline_s),
        )

    def _make_link(
        self,
        source_id: str,
        target_id: str,
        source: Position,
        target: Position,
        radio_range_m: float,
        bandwidth_mbps: float,
        task: Task,
        environment: SimulationEnvironment,
    ) -> Link | None:
        """Create one wireless link, or return None when the target is out of range."""

        raw_loss = environment.packet_loss_probability(source, target, radio_range_m)
        if raw_loss is None:
            return None
        if self.loss_estimator is None:
            loss = raw_loss
        else:
            loss = self.loss_estimator(source_id, target_id, raw_loss, environment.rng)

        expected_attempts = 1.0 / max(0.01, 1.0 - loss)
        expected_retransmissions = max(0.0, expected_attempts - 1.0)
        tx_delay = (task.data_size_mbits / bandwidth_mbps) * expected_attempts
        return Link(
            source_id=source_id,
            target_id=target_id,
            loss_probability=loss,
            tx_delay_s=tx_delay,
            expected_retransmissions=expected_retransmissions,
        )

    def _score(self, delay_s: float, loss_probability: float, deadline_s: float) -> float:
        """Small cost function combining delay, packet loss, and deadline violation."""

        deadline_penalty = 0.0
        if delay_s > deadline_s:
            deadline_penalty = self.config.deadline_weight_s * (delay_s - deadline_s)
        return delay_s + self.config.loss_weight_s * loss_probability + deadline_penalty

    def _apply_processing_load(
        self,
        candidate: OffloadCandidate,
        environment: SimulationEnvironment,
    ) -> None:
        """Add the accepted task's processing time to its selected destination."""

        work_s = candidate.processing_delay_s
        if candidate.destination_type == "vehicle":
            node = environment.get_vehicle(candidate.destination_id)
        elif candidate.destination_type == "provider":
            node = environment.get_provider(candidate.destination_id)
        else:
            node = environment.get_edge(candidate.destination_id)

        fresh_processing_time = work_s - node.queue_s
        node.queue_s += max(0.0, fresh_processing_time)
