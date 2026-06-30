#!/usr/bin/env python3
"""Run Phase 1 simulations for the SDN vehicular edge project."""

from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path
from typing import List

from phase1.config import SCENARIOS, SimulationConfig
from phase1.simulation import run_simulation, write_step_metrics_csv, write_summary_csv


def parse_args() -> object:
    """Read command-line options for scenario, duration, seed, and output path."""

    parser = ArgumentParser(description="Run the Phase 1 vehicular edge simulator.")
    parser.add_argument(
        "--scenario",
        choices=["1", "2", "all"],
        default="all",
        help="Which project scenario to run.",
    )
    parser.add_argument("--steps", type=int, default=120, help="Simulation steps per scenario.")
    parser.add_argument("--seed", type=int, default=7, help="Base random seed.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/phase1"),
        help="Directory for generated CSV files.",
    )
    return parser.parse_args()


def main() -> None:
    """Run selected scenarios and write their CSV outputs."""

    args = parse_args()
    scenario_ids: List[int] = [1, 2] if args.scenario == "all" else [int(args.scenario)]
    summaries = []

    prepare_output_dir(args.output)
    for scenario_id in scenario_ids:
        scenario = SCENARIOS[scenario_id]
        config = replace(
            SimulationConfig(),
            steps=args.steps,
            seed=args.seed + scenario_id,
        )
        summary = run_simulation(scenario, config)
        summaries.append(summary)
        write_step_metrics_csv(
            summary,
            args.output / f"steps_{summary.scenario_name}.csv",
        )

    write_summary_csv(summaries, args.output / "summary.csv")
    print_summary(summaries, args.output)


def prepare_output_dir(output_dir: Path) -> None:
    """Create the output folder and remove stale CSV files from older runs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    for old_csv in output_dir.glob("*.csv"):
        old_csv.unlink()


def print_summary(summaries: list, output_dir: Path) -> None:
    """Print a short terminal table after CSV files are written."""

    print(f"Phase 1 results written to: {output_dir}")
    print()
    print(
        "scenario     tasks  avg_loss  avg_delay_s  missed  blind_spots  provider_avg"
    )
    for summary in summaries:
        provider_avg = (
            f"({summary.average_provider_x:.1f}, {summary.average_provider_y:.1f})"
        )
        print(
            f"{summary.scenario_name:<12}"
            f"{summary.task_count:>6}  "
            f"{summary.average_packet_loss:>8.4f}  "
            f"{summary.average_delay_s:>11.4f}  "
            f"{summary.missed_deadlines:>6}  "
            f"{summary.blind_spots:>11}  "
            f"{provider_avg}"
        )


if __name__ == "__main__":
    main()
