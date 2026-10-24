"""Visualization-only SUMO scenario; never changes required course scenarios."""

from phase1.config import ScenarioConfig


# Double scenario 2's infrastructure; 40 cars keep the smaller streets readable.
COMPACT_DEMO = ScenarioConfig(
    name="compact_demo", vehicle_count=40, provider_count=12, edge_count=8,
)
