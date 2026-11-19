from app.llm.cli import ClaudeCliLlm
from app.llm.offline import OfflineLlm
from app.llm.port import LlmPort
from app.settings import Settings


def build_llm(s: Settings) -> LlmPort:
    """Composition root for the LLM port. New adapters (Anthropic API,
    OpenAI-compatible, FallbackLlm wrapper) slot in here."""
    match s.llm_provider:
        case "offline":
            return OfflineLlm()
        case "claude_cli":
            return ClaudeCliLlm(bin=s.llm_cli_bin, model=s.llm_model,
                                timeout_s=s.llm_timeout_s, extra_args=s.llm_cli_args)
    raise ValueError(f"unknown LLM_PROVIDER: {s.llm_provider}")
