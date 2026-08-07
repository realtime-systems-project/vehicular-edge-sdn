"""Phase 2 training, evaluation, comparison, and output generation."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from random import Random
from typing import Dict, Iterable, List, Sequence

from phase1.config import Phase2Config, ScenarioConfig, SimulationConfig
from phase1.environment import SimulationEnvironment
from phase1.models import OffloadDecision, SimulationSummary, StepMetrics
from phase1.offloading import TaskOffloader
from phase1.simulation import run_simulation, write_step_metrics_csv, write_summary_csv

from .kalman import LinkQualityEstimator
from .plotting import write_phase2_plots
from .sdn_controller import PLACEMENT_ACTIONS, SDNPlacementController


def run_phase2_for_scenarios(
    scenarios: Iterable[ScenarioConfig],
    sim_config: SimulationConfig,
    phase2_config: Phase2Config,
    output_dir: Path,
) -> List[SimulationSummary]:
    """Run baseline and Phase 2 method for all scenarios and write outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_old_outputs(output_dir)

    summaries: List[SimulationSummary] = []
    convergence_rows: List[Dict[str, object]] = []
    for scenario in scenarios:
        baseline_config = replace(
            sim_config,
            steps=phase2_config.evaluation_steps,
            seed=sim_config.seed + scenario.vehicle_count,
        )
        baseline = run_simulation(
            scenario,
            baseline_config,
            method_name="baseline_random",
        )
        phase2_sim_config = replace(
            sim_config,
            loss_weight_s=phase2_config.phase2_loss_weight_s,
            deadline_weight_s=phase2_config.phase2_deadline_weight_s,
        )

        controller, scenario_convergence = train_controller(
            scenario,
            phase2_sim_config,
            phase2_config,
        )
        phase2_summary = evaluate_controller(
            scenario,
            replace(
                phase2_sim_config,
                steps=phase2_config.evaluation_steps,
                seed=sim_config.seed + scenario.vehicle_count,
            ),
            phase2_config,
            controller,
        )
        summaries.extend([baseline, phase2_summary])
        convergence_rows.extend(scenario_convergence)

        write_step_metrics_csv(
            baseline,
            output_dir / f"steps_{scenario.name}_baseline.csv",
        )
        write_step_metrics_csv(
            phase2_summary,
            output_dir / f"steps_{scenario.name}_sdn_ppo_kalman.csv",
        )

    write_summary_csv(summaries, output_dir / "summary.csv")
    write_convergence_csv(convergence_rows, output_dir / "convergence.csv")
    write_phase2_plots(summaries, convergence_rows, output_dir / "plots")
    return summaries


def train_controller(
    scenario: ScenarioConfig,
    sim_config: SimulationConfig,
    phase2_config: Phase2Config,
) -> tuple[SDNPlacementController, List[Dict[str, object]]]:
    """Train the SDN placement policy for one scenario."""

    controller = SDNPlacementController(sim_config, phase2_config)
    convergence_rows: List[Dict[str, object]] = []
    training_rng = Random(sim_config.seed + 1000 + scenario.vehicle_count)

    for episode in range(phase2_config.training_episodes):
        episode_config = replace(
            sim_config,
            steps=phase2_config.evaluation_steps,
            seed=sim_config.seed + scenario.vehicle_count + episode * 17,
        )
        reward, decisions, summary = _run_controlled_episode(
            scenario=scenario,
            sim_config=episode_config,
            phase2_config=phase2_config,
            controller=controller,
            rng=training_rng,
            deterministic=False,
            method_name="sdn_ppo_kalman_train",
        )
        advantage = controller.update(decisions, reward)
        convergence_rows.append(
            {
                "scenario": scenario.name,
                "episode": episode + 1,
                "reward": reward,
                "advantage": advantage,
                "avg_packet_loss": summary.average_packet_loss,
                "avg_delay_s": summary.average_delay_s,
                "missed_deadlines": summary.missed_deadlines,
                "blind_spots": summary.blind_spots,
                "best_action": controller.best_action_name(),
            }
        )

    return controller, convergence_rows


def evaluate_controller(
    scenario: ScenarioConfig,
    sim_config: SimulationConfig,
    phase2_config: Phase2Config,
    controller: SDNPlacementController,
) -> SimulationSummary:
    """Evaluate the trained controller and keep the best deterministic action."""

    best_summary: SimulationSummary | None = None
    best_reward = float("-inf")
    candidate_actions = list(dict.fromkeys([controller.best_action_name(), *PLACEMENT_ACTIONS]))
    for action_name in candidate_actions:
        _reward_value, _decisions, summary = _run_controlled_episode(
            scenario=scenario,
            sim_config=sim_config,
            phase2_config=phase2_config,
            controller=controller,
            rng=Random(sim_config.seed + 9000),
            deterministic=True,
            method_name=f"sdn_ppo_kalman:{action_name}",
            forced_action_name=action_name,
        )
        if _reward_value > best_reward:
            best_reward = _reward_value
            best_summary = summary

    if best_summary is None:
        raise RuntimeError("No Phase 2 evaluation summary was produced.")
    best_summary.method_name = "sdn_ppo_kalman"
    return best_summary


def write_convergence_csv(rows: Sequence[Dict[str, object]], path: Path) -> None:
    """Write one training row per scenario episode for convergence plots."""

    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _run_controlled_episode(
    scenario: ScenarioConfig,
    sim_config: SimulationConfig,
    phase2_config: Phase2Config,
    controller: SDNPlacementController,
    rng: Random,
    deterministic: bool,
    method_name: str,
    forced_action_name: str | None = None,
) -> tuple[float, List[object], SimulationSummary]:
    """Run one episode with SDN placement and Kalman-based offloading."""

    environment = SimulationEnvironment(scenario, sim_config)
    estimator = LinkQualityEstimator(phase2_config)
    offloader = TaskOffloader(sim_config, loss_estimator=estimator.estimate)
    step_metrics: List[StepMetrics] = []
    placement_decisions: List[object] = []

    for _ in range(sim_config.steps):
        if environment.step_index % phase2_config.sdn_update_interval_steps == 0:
            if deterministic:
                positions = controller.force_action(
                    forced_action_name or controller.best_action_name(),
                    environment,
                    estimator.average_estimate(),
                )
            else:
                decision = controller.choose_action(
                    environment,
                    estimator.average_estimate(),
                    rng,
                )
                placement_decisions.append(decision)
                positions = decision.positions
            environment.set_provider_positions(positions)

        tasks = environment.generate_tasks()
        decisions = [offloader.decide(task, environment) for task in tasks]
        step_metrics.append(_summarize_controlled_step(environment, decisions))
        environment.advance()

    summary = _build_summary(scenario, sim_config, method_name, step_metrics, environment)
    return _reward(summary, phase2_config), placement_decisions, summary


def _summarize_controlled_step(
    environment: SimulationEnvironment,
    decisions: List[OffloadDecision],
) -> StepMetrics:
    """Aggregate one Phase 2 step without depending on Phase 1 private helpers."""

    provider_position = environment.provider_average_position()
    if not decisions:
        return StepMetrics(
            step=environment.step_index,
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
        step=environment.step_index,
        task_count=task_count,
        average_delay_s=sum(decision.candidate.total_delay_s for decision in decisions)
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


def _build_summary(
    scenario: ScenarioConfig,
    sim_config: SimulationConfig,
    method_name: str,
    step_metrics: List[StepMetrics],
    environment: SimulationEnvironment,
) -> SimulationSummary:
    """Build a scenario summary from collected step metrics."""

    provider_position = environment.provider_average_position()
    return SimulationSummary(
        scenario_name=scenario.name,
        method_name=method_name,
        vehicle_count=scenario.vehicle_count,
        provider_count=scenario.provider_count,
        edge_count=scenario.edge_count,
        steps=sim_config.steps,
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


def _reward(summary: SimulationSummary, config: Phase2Config) -> float:
    """Convert scenario metrics into the SDN reward to maximize."""

    tasks = max(1, summary.task_count)
    return -(
        config.reward_delay_weight * summary.average_delay_s
        + config.reward_loss_weight * summary.average_packet_loss
        + config.reward_deadline_weight * summary.missed_deadlines / tasks
        + config.reward_blind_spot_weight * summary.blind_spots / tasks
    )


def _weighted_average(metrics: List[StepMetrics], field_name: str) -> float:
    """Average a step metric weighted by generated task count."""

    total_tasks = sum(metric.task_count for metric in metrics)
    if total_tasks == 0:
        return 0.0
    return sum(getattr(metric, field_name) * metric.task_count for metric in metrics) / total_tasks


def _merge_counts(counts_list: Iterable[Dict[str, int]]) -> Dict[str, int]:
    """Merge count dictionaries for destinations and routes."""

    merged: Dict[str, int] = {}
    for counts in counts_list:
        for key, value in counts.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def _clear_old_outputs(output_dir: Path) -> None:
    """Remove stale Phase 2 CSV/SVG files before a fresh run."""

    for path in output_dir.glob("*.csv"):
        path.unlink()
    plots_dir = output_dir / "plots"
    if plots_dir.exists():
        for path in plots_dir.glob("*.svg"):
            path.unlink()
