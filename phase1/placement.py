"""Provider placement policies.

Phase 1 requires a random placement method. The function below is intentionally
small so Phase 2 can add an SDN/PPO placement policy with the same return type.
"""

from random import Random
from typing import List

from .config import SimulationConfig
from .models import Position, ProviderVehicle


def random_provider_placement(
    provider_count: int,
    compute_gps: float,
    config: SimulationConfig,
    rng: Random,
) -> List[ProviderVehicle]:
    """Place provider vehicles uniformly in the two-dimensional area.

    This is the required Phase 1 placement baseline. It is intentionally
    separated from the environment so Phase 2 can replace it with an SDN/PPO
    controller without changing the rest of the simulator.
    """

    return [
        ProviderVehicle(
            node_id=index,
            position=Position(
                x=rng.uniform(0.0, config.area_width_m),
                y=rng.uniform(0.0, config.area_height_m),
            ),
            compute_gps=compute_gps,
        )
        for index in range(provider_count)
    ]
