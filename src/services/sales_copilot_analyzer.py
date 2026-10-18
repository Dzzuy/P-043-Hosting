"""On-demand versioned customer analysis."""

from src.services.intelligence_engine import IntelligenceEngine


class SalesCopilotAnalyzer:
    def __init__(self, repository):
        self.repository = repository

    async def analyze_conversation(self, conversation_id, advisor_id):
        return await IntelligenceEngine(self.repository).analyze(conversation_id, advisor_id)
