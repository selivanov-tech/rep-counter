"""Adapter over a local CLI (`claude -p`). No shell; the prompt goes in on stdin."""

import asyncio
import json
import re
import shlex
import time

from app.llm.port import LlmError, LlmMessage, LlmResult, LlmUsage

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_BODY_EXCERPT = 500


class ClaudeCliLlm:
    def __init__(self, *, bin: str = "claude", model: str = "", timeout_s: float = 60.0,
                 extra_args: str = "") -> None:
        self._bin = bin
        self._model = model
        self._timeout_s = timeout_s
        self._extra = shlex.split(extra_args)

    def build_argv(self, system: str) -> list[str]:
        argv = [self._bin, "-p", "--output-format", "json"]
        if self._model:
            argv += ["--model", self._model]
        if system:
            argv += ["--append-system-prompt", system]
        return argv + self._extra

    async def complete(self, messages: list[LlmMessage], *, max_tokens: int = 512,
                       json_mode: bool = False) -> LlmResult:
        # max_tokens: the CLI has no flag for it; kept for port compatibility.
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        prompt = "\n\n".join(
            m.content if m.role == "user" else f"[{m.role}]\n{m.content}"
            for m in messages if m.role != "system")
        if json_mode:
            prompt += "\n\nReply with JSON only, no prose and no code fence."

        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.build_argv(system), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except FileNotFoundError as exc:
            raise LlmError(f"CLI not found: {self._bin}") from exc
        try:
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode()),
                                              self._timeout_s)
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise LlmError(f"CLI timed out after {self._timeout_s}s") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if proc.returncode != 0:
            raise LlmError("CLI exited with an error", status=proc.returncode,
                           body=err.decode(errors="replace")[:_BODY_EXCERPT])
        return self._parse(out.decode(errors="replace"), latency_ms, json_mode)

    @staticmethod
    def _parse(raw: str, latency_ms: int, json_mode: bool) -> LlmResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LlmError("CLI output is not JSON", body=raw[:_BODY_EXCERPT]) from exc
        if data.get("is_error"):
            raise LlmError("CLI reported an error", body=str(data.get("result"))[:_BODY_EXCERPT])
        text = str(data.get("result", ""))
        if json_mode:
            m = _FENCE.match(text)
            text = m.group(1) if m else text.strip()
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise LlmError("model reply is not valid JSON",
                               body=text[:_BODY_EXCERPT]) from exc
        usage = data.get("usage") or {}
        return LlmResult(text, LlmUsage(
            tokens_in=usage.get("input_tokens"), tokens_out=usage.get("output_tokens"),
            latency_ms=latency_ms, cost_usd=data.get("total_cost_usd")))
