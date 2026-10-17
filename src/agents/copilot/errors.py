"""Copilot errors."""

from src.agents.copilot.runtime import CopilotDependencyError


class CopilotModelOutputError(CopilotDependencyError):
    """A model response failed its contract; never includes raw content."""

    def __init__(self):
        super().__init__("model output contract invalid")
