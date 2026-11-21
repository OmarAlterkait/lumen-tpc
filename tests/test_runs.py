"""The run modes: physical (the default, the detector file as converted) and a reference's run settings."""

import pytest

from lumen_tpc import runs


class _Params(dict):
    def scale(self, key, factor):
        return _Params({**self, key: self[key] * factor})

    def set(self, key, value):
        return _Params({**self, key: value})


def test_the_physical_run_is_the_default_and_changes_nothing():
    run = runs.config("sbnd")
    p = _Params({"materials/LAr/SCINTILLATIONYIELD": 24000.0})
    assert run.lights == ("scintillation", "cherenkov") and run.params(p) == p


def test_sbnd_gdml_run_is_the_scintillation_geant4_reads_from_its_gdml():
    """The yield and the fast share as the GDML writes them (720 /MeV, YIELDRATIO 0.27), not sbndcode's LArSoft's."""
    run = runs.config("sbnd", "gdml")
    assert run.lights == ("scintillation", "cherenkov") and "sbnd_v02_00_full_simulation.gdml" in run.source
    lar = "materials/LAr/SCINTILLATIONYIELD"
    p = run.params(_Params({lar: 24000.0, f"{lar}1": 0.23, f"{lar}2": 0.77}))
    assert p[lar] == 720.0 and p[f"{lar}1"] == 0.27 and p[f"{lar}2"] == 0.73  # the GDML's values


def test_a_run_a_detector_has_not_is_refused():
    with pytest.raises(ValueError, match="no run 'larsoft'"):
        runs.config("microboone", "larsoft")
    with pytest.raises(ValueError, match="lights"):
        runs.Run("x", ("muons",))
