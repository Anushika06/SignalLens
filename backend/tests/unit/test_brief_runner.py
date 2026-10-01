"""aiKart runtime contract and remote delegation (signallens aikart-run)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from signallens.brief import runner
from signallens.brief.reader import DirectReader
from signallens.config import Settings
from tests.brief_scenario import make_world

REMOTE = "https://agent.example.com"


def _settings(**kw) -> Settings:
    base = dict(env="test", llm_provider="none", search_provider="none", nvidia_api_key=None, tavily_api_key=None,
                exa_api_key=None, serper_api_key=None, public_app_url="https://app.test", remote_agent_url=None,
                brief_timeout_s=60)
    return Settings(**{**base, **kw})


@pytest.fixture
def aikart_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKART_DIR", str(tmp_path))
    monkeypatch.delenv("AIKART_INPUT", raising=False)
    monkeypatch.setattr(runner, "AIKART_DIR", tmp_path / "no-such-aikart")  # never touch a real /aikart
    return tmp_path


def _output(path) -> dict:
    out = json.loads((path / "output.json").read_text(encoding="utf-8"))
    assert set(out) == {"format", "response"} and out["format"] == "markdown"
    return out


def test_not_configured_writes_friendly_markdown_and_exits_0(aikart_dir, monkeypatch):
    monkeypatch.setattr(runner, "get_settings", lambda: _settings())
    (aikart_dir / "input.json").write_text(json.dumps({"company": "Razorpay"}), encoding="utf-8")
    assert runner.aikart_main() == 0
    md = _output(aikart_dir)["response"]
    assert "not configured" in md and "NVIDIA_API_KEY" in md and "https://app.test" in md


def test_missing_and_invalid_input_still_write_output(aikart_dir, monkeypatch):
    monkeypatch.setattr(runner, "get_settings", lambda: _settings())
    assert runner.aikart_main() == 0
    assert "No input was provided" in _output(aikart_dir)["response"]
    (aikart_dir / "input.json").write_text("{not json", encoding="utf-8")
    assert runner.aikart_main() == 0
    assert "not valid JSON" in _output(aikart_dir)["response"]
    (aikart_dir / "input.json").write_text(json.dumps({"focus": "Everything"}), encoding="utf-8")
    assert runner.aikart_main() == 0
    assert "Missing 'company'" in _output(aikart_dir)["response"]


def test_env_input_is_used_when_no_file(aikart_dir, monkeypatch):
    monkeypatch.setattr(runner, "get_settings", lambda: _settings())
    monkeypatch.setenv("AIKART_INPUT", json.dumps({"company": "PhonePe"}))
    raw, out = runner.aikart_paths()
    assert raw == {"company": "PhonePe"} and out == aikart_dir / "output.json"


def test_unwritable_output_exits_nonzero(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("AIKART_DIR", str(blocker / "sub"))  # parent is a file: cannot create
    monkeypatch.setattr(runner, "AIKART_DIR", tmp_path / "no-such-aikart")
    monkeypatch.setenv("AIKART_INPUT", "Razorpay")
    monkeypatch.setattr(runner, "get_settings", lambda: _settings())
    assert runner.aikart_main() == 1


@respx.mock
async def test_remote_delegation_posts_inputs_and_returns_markdown():
    route = respx.post(f"{REMOTE}/api/agent/brief").mock(return_value=httpx.Response(
        200, json={"format": "markdown", "response": "# Razorpay — intelligence brief\n", "brief_id": "x"}))
    md = await runner.produce_markdown({"company": "Razorpay", "language": "Hindi"},
                                       _settings(remote_agent_url=REMOTE + "/", remote_agent_key="k1"))
    assert md.startswith("# Razorpay")
    req = route.calls.last.request
    assert req.headers["x-api-key"] == "k1"
    assert json.loads(req.content)["language"] == "Hindi"


@respx.mock
async def test_remote_failure_becomes_markdown():
    respx.post(f"{REMOTE}/api/agent/brief").mock(return_value=httpx.Response(429, json={"detail": "Rate limit"}))
    md = await runner.produce_markdown({"company": "Razorpay"}, _settings(remote_agent_url=REMOTE))
    assert "hosted agent unavailable" in md and "429" in md


async def test_local_run_when_keys_are_present(monkeypatch):
    world = make_world()
    tools = runner.LocalTools(llm=world["llm"], search=world["search"], fetcher=world["fetcher"],
                              wayback=world["wayback"])
    monkeypatch.setattr(runner, "build_local_tools", lambda settings: tools)
    monkeypatch.setattr(runner, "make_reader", lambda mode, fetcher, tavily: DirectReader(fetcher))
    md = await runner.produce_markdown({"inputs": {"company": "Nimbus Pay"}}, _settings())
    assert md.startswith("# Nimbus Pay — intelligence brief")
    assert md.rstrip().endswith("https://app.test_")


async def test_local_crash_becomes_markdown(monkeypatch):
    world = make_world()
    tools = runner.LocalTools(llm=world["llm"], search=world["search"], fetcher=world["fetcher"],
                              wayback=world["wayback"])
    monkeypatch.setattr(runner, "build_local_tools", lambda settings: tools)

    async def boom(*a, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(runner, "run_local", boom)
    md = await runner.produce_markdown({"company": "Nimbus Pay"}, _settings())
    assert "could not complete the brief" in md and "RuntimeError" in md
