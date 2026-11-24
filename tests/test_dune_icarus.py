"""DUNE and ICARUS: the shipped DUNE GDMLs are DUNE's (sha256), their value sets load with provenance, FD2 converts
and loads; the ICARUS recipe refuses without its inputs, and the repository holds nothing of ICARUS but its inputs'
provenance and sha256; the run settings (physical, a reference's) apply to a run only."""

import ast
import json
import lzma
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

import lumen
from lumen import sensors
from lumen_tpc import DETECTORS, icarus, inputs, runs
from lumen_tpc.larsoft_scintillation import lar_scintillation

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "lumen_tpc"
DUNE = ("dune_fd1", "dune_fd1_1x2x6", "dune_fd2", "dune_ndlar")
DUNE_SETS = ("dune_fd1_xarapuca", "dune_fd2_xarapuca", "dune_ndlar_arclight")


@pytest.mark.parametrize("name", DUNE)
def test_dune_gdml_is_dunes(name):
    gdml = DETECTORS[name].gdml
    src = inputs.shipped()[gdml.name[: -len(".xz")]]
    with lzma.open(gdml) as f:
        data = f.read()
    assert len(data) == src["bytes"]
    import hashlib

    assert hashlib.sha256(data).hexdigest() == src["sha256"]
    assert src["url"].startswith("https://raw.githubusercontent.com/DUNE/") and src["commit"] in src["url"]


@pytest.mark.parametrize("name", DUNE_SETS)
def test_dune_value_sets_load_with_provenance(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = sensors.read_values(f"lumen_tpc:{name}")
        sensors.model_from_dict(d)
    p = d["provenance"]
    assert p["status"] == "unverified" and p["source"] and "not published" in p["warning"]
    assert d["tts"] is None and d["charge"] is None  # no public number: left out
    assert abs(sum(d["delay"]["pdf"]) - 1.0) < 1e-9 and d["delay"]["edges_ns"][-1] == 12000.0  # the full table


def test_lar_scintillation_is_larsofts_physical_light():
    """Each experiment's light in Geant4 11 keys, by one rule: ScintYield and ScintYieldRatio, or the muon's when its
    fcl sets ScintByParticleType (DUNE, SBND, and ICARUS by its input's record; MicroBooNE is standard_properties)."""
    by_type = {"overrides": {"by_particle_type": {"value": True, "source": "an input's record"}}}
    for name, record, fast in (("microboone", None, 0.3), ("dune", None, 0.23), ("icarus", by_type, 0.23),
                               ("sbnd", None, 0.23)):  # fmt: skip
        s = lar_scintillation(name, record)
        assert set(s) == {"SCINTILLATIONYIELD", "SCINTILLATIONCOMPONENT1", "SCINTILLATIONCOMPONENT2",
                          "SCINTILLATIONTIMECONSTANT1", "SCINTILLATIONTIMECONSTANT2", "SCINTILLATIONYIELD1",
                          "SCINTILLATIONYIELD2", "RESOLUTIONSCALE"}  # fmt: skip
        assert float(s["SCINTILLATIONYIELD"].value) == 24000.0  # ScintYield, no ScintPreScale
        r = s["RESOLUTIONSCALE"]  # ScintResolutionScale: no experiment here overrides it
        assert float(r.value) == 1.0 and "larproperties.fcl:25 (ScintResolutionScale)" in r.note
        assert float(s["SCINTILLATIONYIELD1"].value) == fast and float(s["SCINTILLATIONYIELD2"].value) == 1.0 - fast
        assert float(s["SCINTILLATIONTIMECONSTANT1"].value) == 6.0
        assert float(s["SCINTILLATIONTIMECONSTANT2"].value) == (1300.0 if name == "sbnd" else 1590.0)
        assert np.array_equal(s["SCINTILLATIONCOMPONENT1"].value, s["SCINTILLATIONCOMPONENT2"].value)


def test_every_larsoft_experiment_has_its_fcl_record():
    """One record per LArSoft experiment in the tables (its fcl over standard_properties, each value with its line)."""
    from lumen_tpc import larsoft_optics

    lar = larsoft_optics.data()["lar"]
    assert set(lar) == {larsoft_optics.STANDARD, "dune", "microboone", "sbnd"}
    for name in ("dune", "microboone", "sbnd"):
        assert lar[name]["table"] and all(":" in o["source"] for o in lar[name]["overrides"].values())
    with pytest.raises(ValueError, match="no LArSoft experiment"):
        lar_scintillation("nonexistent")


@pytest.mark.slow  # a full far-detector conversion
def test_dune_fd2_converts_and_loads(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        det = lumen.load(lumen.convert("lumen_tpc:dune_fd2", out=tmp_path / "fd2.lumen", data=tmp_path))
    assert len(det.sensor_table().name) == 672
    assert float(np.asarray(det.params()["materials/LAr/SCINTILLATIONYIELD"])) == 24000.0


# ------------------------------------------------------------------------------------------------------------ ICARUS
def test_icarus_refuses_without_its_inputs(tmp_path):
    with pytest.raises(inputs.InputError) as e:
        lumen.convert("lumen_tpc:icarus", out=tmp_path / "icarus.lumen", data=tmp_path)
    msg = str(e.value)
    for name, i in icarus.INPUTS.items():
        assert f"{name}: {tmp_path / i['file']} is missing" in msg and i["sha256"] in msg
    assert not (tmp_path / "icarus.lumen").exists()


def test_icarus_refuses_another_file(tmp_path):
    for i in icarus.INPUTS.values():
        (tmp_path / i["file"]).write_text("not ICARUS's\n")
    with pytest.raises(inputs.InputError, match=r"gdml: .* has sha256 [0-9a-f]{64}, not the expected"):
        lumen.convert("lumen_tpc:icarus", out=tmp_path / "icarus.lumen", data=tmp_path)


def _files():
    skip = {".git", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    return [p for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]


def test_nothing_of_icarus_but_provenance_and_sha256():
    """ICARUS's inputs are never in the repository: only icarus.py names its inputs (file, sha256, provenance);
    elsewhere ICARUS is named, never described (no data file, no number of it)."""
    allowed = {"src/lumen_tpc/icarus.py", "src/lumen_tpc/__init__.py", "src/lumen_tpc/runs.py",
               "tests/test_dune_icarus.py", "README.md", "pyproject.toml", "docs/icarus.md",
               "docs/detectors.md"}  # fmt: skip
    seen = set()
    for p in _files():
        rel = p.relative_to(ROOT).as_posix()
        assert "icarus" not in p.name.lower() or rel in allowed, rel
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue
        if re.search("icarus", text, re.I):
            seen.add(rel)
    assert seen <= allowed, sorted(seen - allowed)
    # the recipe holds no number: its only literals are names, file names, sha256 and provenance text
    tree = ast.parse((PKG / "icarus.py").read_text())
    numbers = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
               and not isinstance(n.value, bool)]  # fmt: skip
    assert numbers == []
    shas = [i["sha256"] for i in icarus.INPUTS.values()]
    assert all(re.fullmatch("[0-9a-f]{64}", s) for s in shas)
    # the run module names ICARUS only to say which input holds its runs
    lines = [ln for ln in (PKG / "runs.py").read_text().splitlines() if "icarus" in ln.lower()]
    assert len(lines) == 1 and lines[0].startswith('RUNS_INPUT = {"icarus": "optics"}')


# -------------------------------------------------------------------------------------------------------------- runs
class _Params(dict):
    def scale(self, key, factor):
        return _Params({**self, key: self[key] * factor})


def test_physical_run_is_the_default_and_changes_nothing():
    run = runs.config("dune_fd1")
    p = _Params({"materials/LAr/SCINTILLATIONYIELD": 24000.0})
    assert run.lights == ("scintillation", "cherenkov") and run.params(p) == p


def test_dune_larsoft_run_takes_its_fcl_settings():
    run = runs.config("dune_fd2", "larsoft")
    assert run.lights == ("scintillation",)  # EnableCerenkovLight false
    p = run.params(_Params({"materials/LAr/SCINTILLATIONYIELD": 24000.0}))
    assert p["materials/LAr/SCINTILLATIONYIELD"] == pytest.approx(1200.0)  # ScintPreScale 0.05
    assert "larproperties_dune.fcl" in run.source


def test_reference_runs_are_named_and_refused_otherwise(tmp_path):
    with pytest.raises(ValueError, match="no run 'larsoft'"):
        runs.config("dune_ndlar", "larsoft")
    with pytest.raises(ValueError, match="pass inputs="):
        runs.config("icarus", "larsoft")
    rec = {"runs": {"larsoft": {"lights": ["scintillation"], "scale": {"k": 0.5}, "source": "s"}}}
    (tmp_path / "o.json").write_text(json.dumps(rec))
    run = runs.config("icarus", "larsoft", inputs={"optics": tmp_path / "o.json"})
    assert run.params(_Params({"k": 2.0})) == {"k": 1.0} and run.lights == ("scintillation",)
    with pytest.raises(ValueError, match="lights"):
        runs.Run("x", ("muons",))
