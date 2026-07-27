from opswitness.config import ConsoleConfig
from opswitness.console.aionui import AionUiClient
from opswitness.paperclip import PaperclipClient
from opswitness.runtime_boundaries import AgentRuntime, GovernanceProjection


def test_alpha_adapters_satisfy_the_stable_replacement_boundaries():
    aion = AionUiClient(ConsoleConfig())
    governance = PaperclipClient(
        "http://127.0.0.1:65535",
        "non-secret-test-key",
        "test-company",
    )

    assert isinstance(aion, AgentRuntime)
    assert isinstance(governance, GovernanceProjection)
