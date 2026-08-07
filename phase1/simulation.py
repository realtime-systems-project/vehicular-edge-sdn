"""Simulation runner and CSV output helpers.

The module keeps Phase 1 baseline execution available and also exposes summary
helpers reused by the Phase 2 comparison runner.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List

from .config import ScenarioConfig, SimulationConfig
from .environment import SimulationEnvironment
from .models import OffloadDecision, SimulationSummary, StepMetrics
from .offloading import TaskOffloader


def run_simulation(
    scenario: ScenarioConfig,
    config: SimulationConfig,
    method_name: str = "baseline",
) -> SimulationSummary:
    """Run one scenario and return both per-step and whole-run metrics."""

    environment = SimulationEnvironment(scenario, config)
    offloader = TaskOffloader(config)
    step_metrics: List[StepMetrics] = []

    for _ in range(config.steps):
        tasks = environment.generate_tasks()
        decisions = [offloader.decide(task, environment) for task in tasks]
        step_metrics.append(_summarize_step(environment, decisions))
        environment.advance()

    provider_position = environment.provider_average_position()
    return SimulationSummary(
        scenario_name=scenario.name,
        method_name=method_name,
        vehicle_count=scenario.vehicle_count,
        provider_count=scenario.provider_count,
        edge_count=scenario.edge_count,
        steps=config.steps,
        task_count=sum(metric.task_count for metric in step_metrics),
        average_delay_s=_weighted_average(step_metrics, "average_delay_s"),
        average_packet_loss=_weighted_average(step_metrics, "average_packet_loss"),
        expected_retransmissions=sum(metric.expected_retransmissions for metric in step_metrics),
        missed_deadlines=sum(metric.missed_deadlines for metric in step_metrics),
        blind_spots=sum(metric.blind_spots for metric in step_metrics),
        average_provider_x=provider_position.x,
        average_provider_y=provider_position.y,
        destination_counts=_merge_counts(metric.destination_counts for metric in step_metrics),
        route_counts=_merge_counts(metric.route_counts for metric in step_metrics),
        step_metrics=step_metrics,
    )


def write_summary_csv(summaries: Iterable[SimulationSummary], path: Path) -> None:
    """Write one compact CSV row per scenario."""

    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(summaries)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario",
                "method",
                "vehicles",
                "providers",
                "edge_servers",
                "steps",
                "tasks",
                "avg_packet_loss",
                "avg_delay_s",
                "expected_retransmissions",
                "missed_deadlines",
                "blind_spots",
                "avg_provider_x",
                "avg_provider_y",
                "destination_counts",
                "route_counts",
            ],
        )
        writer.writeheader()
        for summary in rows:
            writer.writerow(
                {
                    "scenario": summary.scenario_name,
                    "method": summary.method_name,
                    "vehicles": summary.vehicle_count,
                    "providers": summary.provider_count,
                    "edge_servers": summary.edge_count,
                    "steps": summary.steps,
                    "tasks": summary.task_count,
                    "avg_packet_loss": f"{summary.average_packet_loss:.6f}",
                    "avg_delay_s": f"{summary.average_delay_s:.6f}",
                    "expected_retransmissions": f"{summary.expected_retransmissions:.6f}",
                    "missed_deadlines": summary.missed_deadlines,
                    "blind_spots": summary.blind_spots,
                    "avg_provider_x": f"{summary.average_provider_x:.3f}",
                    "avg_provider_y": f"{summary.average_provider_y:.3f}",
                    "destination_counts": _format_counts(summary.destination_counts),
                    "route_counts": _format_counts(summary.route_counts),
                }
            )


def write_step_metrics_csv(summary: SimulationSummary, path: Path) -> None:
    """Write time-series metrics for one scenario."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "step",
                "tasks",
                "avg_packet_loss",
                "avg_delay_s",
                "expected_retransmissions",
                "missed_deadlines",
                "blind_spots",
                "avg_provider_x",
                "avg_provider_y",
                "destination_counts",
                "route_counts",
            ],
        )
        writer.writeheader()
        for metric in summary.step_metrics:
            writer.writerow(
                {
                    "step": metric.step,
                    "tasks": metric.task_count,
                    "avg_packet_loss": f"{metric.average_packet_loss:.6f}",
                    "avg_delay_s": f"{metric.average_delay_s:.6f}",
                    "expected_retransmissions": f"{metric.expected_retransmissions:.6f}",
                    "missed_deadlines": metric.missed_deadlines,
                    "blind_spots": metric.blind_spots,
                    "avg_provider_x": f"{metric.average_provider_x:.3f}",
                    "avg_provider_y": f"{metric.average_provider_y:.3f}",
                    "destination_counts": _format_counts(metric.destination_counts),
                    "route_counts": _format_counts(metric.route_counts),
                }
            )


def _summarize_step(
    environment: SimulationEnvironment,
    decisions: List[OffloadDecision],
) -> StepMetrics:
    """Convert task-level decisions into one row of step-level metrics."""

    provider_position = environment.provider_average_position()
    step = environment.step_index
    if not decisions:
        return StepMetrics(
            step=step,
            average_provider_x=provider_position.x,
            average_provider_y=provider_position.y,
        )

    destination_counts: Dict[str, int] = {}
    route_counts: Dict[str, int] = {}
    for decision in decisions:
        destination = decision.candidate.destination_type
        route = decision.candidate.route_name
        destination_counts[destination] = destination_counts.get(destination, 0) + 1
        route_counts[route] = route_counts.get(route, 0) + 1

    task_count = len(decisions)
    return StepMetrics(
        step=step,
        task_count=task_count,
        average_delay_s=sum(
            decision.candidate.total_delay_s for decision in decisions
        )
        / task_count,
        average_packet_loss=sum(
            decision.candidate.packet_loss_probability for decision in decisions
        )
        / task_count,
        expected_retransmissions=sum(
            decision.candidate.expected_retransmissions for decision in decisions
        ),
        missed_deadlines=sum(1 for decision in decisions if decision.candidate.missed_deadline),
        blind_spots=sum(1 for decision in decisions if decision.blind_spot),
        average_provider_x=provider_position.x,
        average_provider_y=provider_position.y,
        destination_counts=destination_counts,
        route_counts=route_counts,
    )


def _weighted_average(metrics: List[StepMetrics], field_name: str) -> float:
    """Average a per-step metric weighted by how many tasks occurred per step."""

    total_tasks = sum(metric.task_count for metric in metrics)
    if total_tasks == 0:
        return 0.0
    weighted_sum = sum(
        getattr(metric, field_name) * metric.task_count for metric in metrics
    )
    return weighted_sum / total_tasks


def _merge_counts(counts_list: Iterable[Dict[str, int]]) -> Dict[str, int]:
    """Merge dictionaries such as destination or route counters."""

    merged: Dict[str, int] = {}
    for counts in counts_list:
        for key, value in counts.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def _format_counts(counts: Dict[str, int]) -> str:
    """Store counters in CSV as a compact `key:value;key:value` string."""

    if not counts:
        return ""
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))
