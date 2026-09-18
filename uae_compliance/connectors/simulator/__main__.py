"""Run the simulator on its own, for the demo path.

	python -m uae_compliance.connectors.simulator --store /tmp/sim.db

It listens on loopback and prints the address to point a connection at. It is
not a service and there is nothing to deploy.
"""

from __future__ import annotations

import argparse

from uae_compliance.connectors.simulator.behaviour import PROFILES
from uae_compliance.connectors.simulator.server import Simulator, SimulatorServer
from uae_compliance.connectors.simulator.store import Store


def main() -> None:
	parser = argparse.ArgumentParser(description="Run the local provider simulator")
	parser.add_argument("--store", required=True, help="Path to the simulator's file")
	parser.add_argument("--port", type=int, default=0)
	parser.add_argument("--profile", choices=sorted(PROFILES), default="full")
	parser.add_argument("--callback-url", default=None)
	options = parser.parse_args()

	simulator = Simulator(Store(options.store), PROFILES[options.profile], options.callback_url)
	server = SimulatorServer(simulator, port=options.port).start()
	print(f"Simulation provider on {server.base_url}, profile {options.profile}", flush=True)
	try:
		server.wait()
	except KeyboardInterrupt:
		server.stop()


if __name__ == "__main__":
	main()
