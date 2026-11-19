import json
import stat
import sys

import pytest

from app.llm.cli import ClaudeCliLlm
from app.llm.factory import build_llm
from app.llm.offline import OfflineLlm
from app.llm.port import LlmError, LlmMessage
from app.settings import Settings


def fake_cli(tmp_path, body: str, code: int = 0, sleep: float = 0):
    """A stand-in for `claude` that echoes argv/stdin info and prints `body`."""
    p = tmp_path / "fake-claude"
    p.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "sys.stdin.read()\n"
        f"time.sleep({sleep})\n"
        f"sys.stdout.write({body!r})\n"
        f"sys.exit({code})\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


MSGS = [LlmMessage("system", "be brief"), LlmMessage("user", "hi")]


def test_factory_switches_on_settings():
    assert isinstance(build_llm(Settings(llm_provider="offline")), OfflineLlm)
    llm = build_llm(Settings(llm_provider="claude_cli", llm_cli_bin="x", llm_model="m"))
    assert isinstance(llm, ClaudeCliLlm)


def test_argv():
    llm = ClaudeCliLlm(bin="claude", model="sonnet", extra_args="--max-turns 1")
    assert llm.build_argv("sys") == [
        "claude", "-p", "--output-format", "json", "--model", "sonnet",
        "--append-system-prompt", "sys", "--max-turns", "1"]


async def test_offline_raises():
    with pytest.raises(LlmError):
        await OfflineLlm().complete(MSGS)


async def test_cli_success(tmp_path):
    body = json.dumps({"result": "hello", "usage": {"input_tokens": 3, "output_tokens": 1},
                       "total_cost_usd": 0.001})
    res = await ClaudeCliLlm(bin=fake_cli(tmp_path, body)).complete(MSGS)
    assert res.text == "hello"
    assert res.usage.tokens_in == 3 and res.usage.cost_usd == 0.001


async def test_cli_json_mode_strips_fence(tmp_path):
    body = json.dumps({"result": '```json\n{"ok": true}\n```'})
    res = await ClaudeCliLlm(bin=fake_cli(tmp_path, body)).complete(MSGS, json_mode=True)
    assert json.loads(res.text) == {"ok": True}


async def test_cli_json_mode_invalid(tmp_path):
    body = json.dumps({"result": "not json"})
    with pytest.raises(LlmError):
        await ClaudeCliLlm(bin=fake_cli(tmp_path, body)).complete(MSGS, json_mode=True)


async def test_cli_nonzero_exit(tmp_path):
    with pytest.raises(LlmError) as e:
        await ClaudeCliLlm(bin=fake_cli(tmp_path, "", code=2)).complete(MSGS)
    assert e.value.status == 2


async def test_cli_timeout(tmp_path):
    llm = ClaudeCliLlm(bin=fake_cli(tmp_path, "{}", sleep=5), timeout_s=0.3)
    with pytest.raises(LlmError, match="timed out"):
        await llm.complete(MSGS)


async def test_cli_missing_binary():
    with pytest.raises(LlmError, match="not found"):
        await ClaudeCliLlm(bin="/nonexistent/claude").complete(MSGS)
