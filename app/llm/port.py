from dataclasses import dataclass
from typing import Literal, Protocol


class LlmError(Exception):
    """The LLM could not answer: timeout, non-zero exit, unparsable output."""

    def __init__(self, message: str, *, status: int | None = None,
                 body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class LlmMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LlmUsage:
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int
    cost_usd: float | None = None


@dataclass(frozen=True)
class LlmResult:
    text: str
    usage: LlmUsage


class LlmPort(Protocol):
    async def complete(self, messages: list[LlmMessage], *, max_tokens: int = 512,
                       json_mode: bool = False) -> LlmResult: ...
