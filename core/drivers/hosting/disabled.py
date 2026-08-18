from __future__ import annotations

from core.drivers import Deployment
from core.errors import CapabilityDisabled


class DisabledHostingDriver:
    name = "disabled"

    def deploy(self, path: str, project: str) -> Deployment:
        raise CapabilityDisabled("hosting", "deploy intents are Red; sabre setup --step 12")

    def domains(self, project: str) -> list[str]:
        raise CapabilityDisabled("hosting")

    def teardown(self, project: str) -> None:
        raise CapabilityDisabled("hosting")
