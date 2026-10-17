"""Preserve safe provider error codes before the chat adapter discards them."""

from langchain_openai import ChatOpenAI


class ProviderResponseError(RuntimeError):
    def __init__(self, error=None):
        error = error if isinstance(error, dict) else {}
        code = error.get("code")
        self.status_code = int(code) if str(code).isdigit() and 400 <= int(code) <= 599 else None
        metadata = error.get("metadata")
        kind = metadata.get("error_type") if isinstance(metadata, dict) else None
        self.provider_error_kind = (
            kind
            if kind
            in {
                "server",
                "rate_limit_exceeded",
                "provider_unavailable",
                "timeout",
                "invalid_request",
                "authentication",
                "insufficient_credits",
                "content_filter",
            }
            else "upstream_error"
        )
        super().__init__("provider returned an error response")


class CopilotChatOpenAI(ChatOpenAI):
    """Non-streaming Copilot calls: never turn an upstream error into JSON repair."""

    def _create_chat_result(self, response, generation_info=None):
        if not isinstance(response, dict) and not hasattr(response, "model_dump"):
            raise ProviderResponseError()
        raw = response if isinstance(response, dict) else response.model_dump()
        if raw.get("error"):
            raise ProviderResponseError(raw["error"])
        for choice in raw.get("choices") or []:
            if choice.get("finish_reason") == "error" or choice.get("error"):
                raise ProviderResponseError(choice.get("error") or (choice.get("message") or {}).get("error"))
        return super()._create_chat_result(response, generation_info)
