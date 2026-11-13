"""Multilingual indirect-prompt-injection harness built on AgentDojo.

Importing this package registers the multilingual attacks with AgentDojo's
attack registry (see ``ipi_ml.attack``).
"""

from ipi_ml import attack as _attack  # noqa: F401  (registers attacks)
from ipi_ml.constants import BENCHMARK_VERSION, LANGUAGES

__all__ = ["BENCHMARK_VERSION", "LANGUAGES"]
