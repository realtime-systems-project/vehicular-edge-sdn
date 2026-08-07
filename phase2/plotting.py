"""Dependency-free SVG plotting for Phase 2 results."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from phase1.models import SimulationSummary


def write_phase2_plots(
    summaries: Sequence[SimulationSummary],
    convergence_rows: Sequence[Dict[str, object]],
    output_dir: Path,
) -> None:
    """Write all plots required by the project as SVG files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_metric_bar(
        summaries,
        "average_packet_loss",
        "Average packet-loss ratio",
        output_dir / "average_packet_loss.svg",
    )
    _write_metric_bar(
        summaries,
        "average_delay_s",
        "Average system delay (s)",
        output_dir / "average_delay.svg",
    )
    _write_metric_bar(
        summaries,
        "missed_deadlines",
        "Number of missed deadlines",
        output_dir / "missed_deadlines.svg",
    )
    _write_metric_bar(
        summaries,
        "blind_spots",
        "Number of blind-spot occurrences",
        output_dir / "blind_spots.svg",
    )
    _write_provider_scatter(
        summaries,
        output_dir / "average_provider_locations.svg",
    )
    _write_convergence_plot(
        convergence_rows,
        output_dir / "rl_convergence.svg",
    )


def _write_metric_bar(
    summaries: Sequence[SimulationSummary],
    field_name: str,
    title: str,
    path: Path,
) -> None:
    """Create a grouped bar chart comparing baseline and SDN/RL methods."""

    width = 900
    height = 440
    margin_left = 80
    margin_bottom = 80
    plot_width = width - margin_left - 40
    plot_height = height - 70 - margin_bottom
    values = [float(getattr(summary, field_name)) for summary in summaries]
    max_value = max(values) if values else 1.0
    max_value = max(max_value, 1e-9)
    bar_width = plot_width / max(1, len(summaries) * 1.5)

    elements = _svg_header(width, height, title)
    elements.append(_axis(margin_left, 50, plot_width, plot_height))
    for index, summary in enumerate(summaries):
        value = float(getattr(summary, field_name))
        x = margin_left + 18 + index * bar_width * 1.4
        bar_height = (value / max_value) * plot_height
        y = 50 + plot_height - bar_height
        color = "#4C78A8" if "baseline" in summary.method_name else "#2CA02C"
        label = f"{summary.scenario_name}\\n{summary.method_name}"
        elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bar_height:.1f}" fill="{color}" />'
        )
        elements.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" '
            f'text-anchor="middle" font-size="12">{value:.3f}</text>'
        )
        elements.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - 45}" '
            f'text-anchor="middle" font-size="11">{_escape(label)}</text>'
        )
    elements.append(_svg_footer())
    path.write_text("\n".join(elements), encoding="utf-8")


def _write_provider_scatter(summaries: Sequence[SimulationSummary], path: Path) -> None:
    """Create a scatter plot of average provider locations by method."""

    width = 600
    height = 600
    margin = 70
    plot_size = width - 2 * margin
    elements = _svg_header(width, height, "Average provider vehicle locations")
    elements.append(_axis(margin, margin, plot_size, plot_size))
    for summary in summaries:
        x = margin + (summary.average_provider_x / 1000.0) * plot_size
        y = margin + plot_size - (summary.average_provider_y / 1000.0) * plot_size
        color = "#4C78A8" if "baseline" in summary.method_name else "#2CA02C"
        elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}" />')
        elements.append(
            f'<text x="{x + 12:.1f}" y="{y - 8:.1f}" font-size="12">'
            f'{_escape(summary.scenario_name)} {_escape(summary.method_name)}</text>'
        )
    elements.append(
        f'<text x="{width / 2}" y="{height - 20}" text-anchor="middle" '
        f'font-size="12">x coordinate (m), y coordinate (m)</text>'
    )
    elements.append(_svg_footer())
    path.write_text("\n".join(elements), encoding="utf-8")


def _write_convergence_plot(rows: Sequence[Dict[str, object]], path: Path) -> None:
    """Create the RL convergence curve from training rewards."""

    width = 900
    height = 460
    margin_left = 80
    margin_bottom = 70
    plot_width = width - margin_left - 50
    plot_height = height - 70 - margin_bottom
    grouped: Dict[str, List[Tuple[int, float]]] = {}
    for row in rows:
        grouped.setdefault(str(row["scenario"]), []).append(
            (int(row["episode"]), float(row["reward"]))
        )

    values = [reward for series in grouped.values() for _episode, reward in series]
    min_value = min(values) if values else -1.0
    max_value = max(values) if values else 0.0
    if abs(max_value - min_value) < 1e-9:
        max_value += 1.0
    max_episode = max((episode for series in grouped.values() for episode, _ in series), default=1)

    elements = _svg_header(width, height, "RL convergence curve")
    elements.append(_axis(margin_left, 50, plot_width, plot_height))
    colors = ["#4C78A8", "#2CA02C", "#F58518"]
    for color, (scenario, series) in zip(colors, grouped.items()):
        points = []
        for episode, reward in series:
            x = margin_left + ((episode - 1) / max(1, max_episode - 1)) * plot_width
            y = 50 + plot_height - ((reward - min_value) / (max_value - min_value)) * plot_height
            points.append(f"{x:.1f},{y:.1f}")
        elements.append(
            f'<polyline points="{" ".join(points)}" fill="none" '
            f'stroke="{color}" stroke-width="2.5" />'
        )
        if points:
            last_x, last_y = points[-1].split(",")
            elements.append(
                f'<text x="{float(last_x) + 8:.1f}" y="{float(last_y):.1f}" '
                f'font-size="12">{_escape(scenario)}</text>'
            )
    elements.append(_svg_footer())
    path.write_text("\n".join(elements), encoding="utf-8")


def _svg_header(width: int, height: int, title: str) -> List[str]:
    """Return the opening SVG elements and chart title."""

    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white" />',
        f'<text x="{width / 2}" y="28" text-anchor="middle" '
        f'font-size="20" font-family="Arial">{_escape(title)}</text>',
    ]


def _axis(x: int, y: int, width: int, height: int) -> str:
    """Return a simple L-shaped chart axis."""

    return (
        f'<path d="M{x},{y} V{y + height} H{x + width}" '
        f'stroke="#444" stroke-width="1.2" fill="none" />'
    )


def _svg_footer() -> str:
    """Return the SVG closing tag."""

    return "</svg>"


def _escape(value: object) -> str:
    """Escape text for safe SVG output."""

    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

