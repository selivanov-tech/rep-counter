from app.llm.port import LlmError, LlmMessage, LlmResult


class OfflineLlm:
    """Default adapter: no CLI, no keys. Lets tests/CI run; any real call fails loudly."""

    async def complete(self, messages: list[LlmMessage], *, max_tokens: int = 512,
                       json_mode: bool = False) -> LlmResult:
        raise LlmError("llm disabled (LLM_PROVIDER=offline)")
