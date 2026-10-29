"""Render smoke test for the dashboard card (needs node and the pre-installed Playwright)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "frontend" / "smoke.cjs"


def test_card_renders():
    if shutil.which("node") is None:
        pytest.skip("node not available")
    result = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    if "Cannot find module 'playwright'" in result.stderr:
        pytest.skip("playwright not available")
    assert result.returncode == 0, result.stdout + result.stderr
