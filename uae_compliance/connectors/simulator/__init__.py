"""A local provider that is not there, for tests and for the demo path.

It is test infrastructure. Nothing in the app depends on it and nothing it
issues works anywhere else: credentials start with `sim_`, identifiers start
with `SIM-`, and a Production connection refuses both.
"""

from uae_compliance.connectors.simulator.behaviour import BARE, FULL, Behaviour, Profile
from uae_compliance.connectors.simulator.server import CallbackSink, Simulator, SimulatorServer
from uae_compliance.connectors.simulator.store import ACCEPTED_LABEL, ENVIRONMENT, Store

__all__ = [
	"ACCEPTED_LABEL",
	"BARE",
	"ENVIRONMENT",
	"FULL",
	"Behaviour",
	"CallbackSink",
	"Profile",
	"Simulator",
	"SimulatorServer",
	"Store",
]
