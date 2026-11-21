"""docs/detectors.md's code runs as written (it converts MicroBooNE, its GDML read from LUMEN_DATA)."""

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.environ.get("LUMEN_DATA"), reason="needs LUMEN_DATA (the GDML, or where to fetch it)")
def test_the_detectors_page_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMEN_EXAMPLES_OUT", str(tmp_path))
    ns: dict = {}
    for code in re.findall(r"```python\n(.*?)```", (ROOT / "docs/detectors.md").read_text(), re.S):
        exec(compile(code, "docs/detectors.md", "exec"), ns)
    assert len(ns["det"].sensor_table().name) > 0
