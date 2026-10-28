"""root_agent for `adk eval`, built from the arguments investigate() gives LlmAgent so the instruction isn't duplicated."""
import asyncio
import sys
from pathlib import Path

from google.adk.agents import LlmAgent

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from agent_service import service  # noqa: E402


class _Captured(Exception):
    def __init__(self, kwargs):
        self.kwargs = kwargs


def _capture(**kwargs):
    raise _Captured(kwargs)


def _build():
    original = service.LlmAgent
    service.LlmAgent = _capture
    try:
        asyncio.run(service.investigate(""))
    except _Captured as captured:
        return LlmAgent(**captured.kwargs)
    finally:
        service.LlmAgent = original
    raise RuntimeError("service.investigate did not construct an LlmAgent")


root_agent = _build()
