"""Kalman-based link quality estimation for Phase 2.

The project asks vehicles to use a Kalman filter to estimate link quality and
predict packet loss. We model each wireless hop as a scalar hidden state: the
current packet-loss probability of that link. Each new noisy measurement updates
the state, and the offloader uses the filtered estimate for decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Dict, Tuple

from phase1.config import Phase2Config


@dataclass
class ScalarKalmanFilter:
    """One-dimensional Kalman filter for a single packet-loss probability."""

    estimate: float
    uncertainty: float
    process_noise: float
    measurement_noise: float

    def update(self, measurement: float) -> float:
        """Predict one step, absorb the measurement, and return the estimate."""

        predicted_uncertainty = self.uncertainty + self.process_noise
        kalman_gain = predicted_uncertainty / (
            predicted_uncertainty + self.measurement_noise
        )
        self.estimate = self.estimate + kalman_gain * (measurement - self.estimate)
        self.uncertainty = (1.0 - kalman_gain) * predicted_uncertainty
        return self.estimate


class LinkQualityEstimator:
    """Maintain Kalman filters for all observed directed wireless links."""

    def __init__(self, config: Phase2Config):
        """Store noise parameters and prepare an empty link-filter table."""

        self.config = config
        self.filters: Dict[Tuple[str, str], ScalarKalmanFilter] = {}

    def estimate(
        self,
        source_id: str,
        target_id: str,
        true_loss: float,
        rng: Random,
    ) -> float:
        """Return the Kalman-smoothed loss estimate for one directed link."""

        measurement = self._noisy_measurement(true_loss, rng)
        key = (source_id, target_id)
        if key not in self.filters:
            self.filters[key] = ScalarKalmanFilter(
                estimate=measurement,
                uncertainty=0.10,
                process_noise=self.config.kalman_process_noise,
                measurement_noise=self.config.kalman_measurement_noise,
            )
        return self._clamp(self.filters[key].update(measurement))

    def average_estimate(self) -> float:
        """Return the mean link-loss estimate used in the SDN controller state."""

        if not self.filters:
            return 0.15
        return sum(filter_.estimate for filter_ in self.filters.values()) / len(
            self.filters
        )

    def _noisy_measurement(self, true_loss: float, rng: Random) -> float:
        """Simulate a noisy packet-loss observation from recent transmissions."""

        noise = rng.gauss(0.0, self.config.kalman_measurement_jitter)
        return self._clamp(true_loss + noise)

    @staticmethod
    def _clamp(value: float, low: float = 0.01, high: float = 0.85) -> float:
        """Keep packet-loss probabilities inside a realistic interval."""

        return max(low, min(high, value))

