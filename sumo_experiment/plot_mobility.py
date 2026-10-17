"""Optional Matplotlib view of recorded SUMO roads and provider trajectories."""

from __future__ import annotations

import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def plot_mobility(output: Path) -> Path:
    """Plot actual provider paths and final car positions for both evaluations.

    Matplotlib is optional and used only by this separate export command; the
    simulator and its six original SVG plots do not require it.
    """

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest = json.loads((output / "manifest.json").read_text())
    network = ET.parse(output / "network" / "grid.net.xml")
    roads = []
    for edge in network.getroot().findall("edge"):
        if edge.get("function") == "internal":
            continue
        lane = edge.find("lane")
        roads.append([tuple(map(float, point.split(","))) for point in lane.get("shape").split()])
    scenarios = manifest["scenarios"]
    figure, axes = plt.subplots(len(scenarios), 2, figsize=(12, 5.5 * len(scenarios)), squeeze=False)
    for row_index, details in enumerate(scenarios):
        scenario = details["scenario"]
        for column, method in enumerate(("baseline", "controlled")):
            axis = axes[row_index, column]
            directory = output / scenario["name"] / method
            with (directory / "mobility.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            last_step = max(int(row["step"]) for row in rows)
            for road in roads:
                axis.plot([point[0] for point in road], [point[1] for point in road],
                          color="#b8bec5", linewidth=1, zorder=1)
            cars = [row for row in rows if row["node"].startswith("vehicle:") and int(row["step"]) == last_step]
            axis.scatter([float(row["x"]) for row in cars], [float(row["y"]) for row in cars],
                         color="#198ca8", s=18, label="Cars at end", zorder=3)
            for provider in range(scenario["provider_count"]):
                trajectory = [row for row in rows if row["node"] == f"provider:{provider}"]
                x, y = [float(row["x"]) for row in trajectory], [float(row["y"]) for row in trajectory]
                color = plt.get_cmap("tab10")(provider)
                axis.plot(x, y, color=color, linewidth=2, label=f"Provider {provider}", zorder=4)
                axis.scatter(x[0], y[0], color=[color], s=50, marker="o", zorder=5)
                axis.scatter(x[-1], y[-1], color=[color], s=65, marker="s", zorder=5)
            width = manifest["simulation"]["area_width_m"]
            height = manifest["simulation"]["area_height_m"]
            for index in range(scenario["edge_count"]):
                axis.scatter((index + 1) * width / (scenario["edge_count"] + 1),
                             height * (0.92 if index % 2 else 0.08),
                             marker="^", color="#198b38", s=80, zorder=6,
                             label="Fixed edge server" if index == 0 else None)
            strategy = f" / {details['selected_strategy']}" if method == "controlled" else ""
            axis.set_title(f"{scenario['name']}: {method}{strategy}", fontsize=11)
            axis.set(xlabel="x (m)", ylabel="y (m)", xlim=(-25, width + 25), ylim=(-25, height + 25))
            axis.set_aspect("equal")
    figure.suptitle("SUMO: actual provider paths (circle = start, square = end)", fontsize=13)
    handles, labels = axes[-1, -1].get_legend_handles_labels()
    figure.legend(handles, labels, loc="lower center", ncol=4, fontsize=9, fancybox=False)
    figure.tight_layout(rect=(0, 0.07, 1, 0.97))
    path = output / "plots" / "mobility.png"
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


if __name__ == "__main__":
    print(plot_mobility(Path(sys.argv[1])))
