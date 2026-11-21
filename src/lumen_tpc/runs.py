"""How a detector is run: physically (the default), or as a reference simulation ran it, for a comparison only.

    run = runs.config("dune_fd1")                       # "physical": every light, the detector's values as converted
    run = runs.config("dune_fd1", "larsoft")            # the experiment's LArSoft run, to compare with its output
    params = run.params(det.params())                   # the run's values (the detector file is unchanged)
    if "cherenkov" in run.lights: ...                   # which lights the run's sources emit

A detector file holds the detector's physics: LAr's full physical scintillation yield, Cherenkov light, no prescale.
An experiment's own simulation may run otherwise (LArSoft's ScintPreScale multiplies the yield before Geant4 and is
divided out of its detection efficiency later; a fcl may switch Cherenkov light off). To compare with that output, the
run takes the reference's settings: a factor on named parameter values (``Params.scale``) and the lights its sources
emit; or a value a reference simulation gave a parameter in place of the detector's (``Params.set``). These are run
settings, never a second detector file or an edit of the detector's physics.

A detector's reference runs are ``REFERENCE_RUNS[name]`` (public settings, with their sources), or, for a detector
whose inputs are given by path, the ``"runs"`` record of its input named in ``RUNS_INPUT`` (``config(..., inputs=)``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

LIGHTS = ("scintillation", "cherenkov")
PHYSICAL = "physical"


@dataclass(frozen=True)
class Run:
    """A run's settings: the lights its sources emit, a factor per parameter key (``Params.scale``) and a value per
    parameter key (``Params.set``, after the factors)."""  # noqa: D205, D209

    name: str = PHYSICAL
    lights: tuple[str, ...] = LIGHTS
    scale: dict = field(default_factory=dict)
    source: str = ""
    values: dict = field(default_factory=dict)

    def __post_init__(self):
        """Check the lights."""
        if not set(self.lights) <= set(LIGHTS):
            raise ValueError(f"run {self.name!r}: lights {self.lights} are not among {LIGHTS}")

    def params(self, params):
        """Return ``params`` with this run's factors applied (each key's value times its factor), then its values."""
        for key, factor in self.scale.items():
            params = params.scale(key, factor)
        for key, value in self.values.items():
            params = params.set(key, value)
        return params

    @classmethod
    def of(cls, name: str, record: dict) -> Run:
        """Return the run of a record ``{"lights": [...], "scale": {key: factor}, "values": {key: value}, "source":
        "..."}``."""  # noqa: D205, D209
        return cls(name, tuple(record.get("lights", LIGHTS)), dict(record.get("scale", {})), record.get("source", ""),
                   dict(record.get("values", {})))  # fmt: skip


DUNE_LARSOFT = {
    "lights": ["scintillation"],
    "scale": {"materials/LAr/SCINTILLATIONYIELD": 0.05},
    "source": "DUNE/dunecore@1861034bf807a2f556a476615c0a0f212dc43a0e dunecore/Utilities/larproperties_dune.fcl:14 "
    "(dunefd_properties.ScintPreScale: 0.05) and :15 (EnableCerenkovLight: false); dunefdvd_properties = "
    "dunefd_properties",
}
# SBND's GDML as written, which Geant4 reads in the g4ref references. Its LAr scintillation differs from the detector
# file's (sbndcode's LArSoft, larsoft.sbnd_scintillation) in two values: SCINTILLATIONYIELD 720 /MeV, lardataalg's
# ScintYield x ScintPreScale (24000 x 0.03; sbndcode's own fcl later sets ScintPreScale 0.0392), and YIELDRATIO 0.27
# (Geant4 11: SCINTILLATIONYIELD1 0.27, SCINTILLATIONYIELD2 0.73) where sbndcode's LArSoft gives the muon's 0.23. Its
# spectra and time constants (6 ns, 1300 ns) are the detector file's. Cherenkov light on
SBND_GDML = {
    "lights": ["scintillation", "cherenkov"],
    "scale": {"materials/LAr/SCINTILLATIONYIELD": 0.03},
    "values": {"materials/LAr/SCINTILLATIONYIELD1": 0.27, "materials/LAr/SCINTILLATIONYIELD2": 0.73},
    "source": "sbnd_v02_00_full_simulation.gdml (sbndcode 4e41b3d8) l.83 (SY 720/MeV), l.87 (YR 0.27), l.85-86 (FTC "
    "6, STC 1300 ns): the LAr scintillation Geant4 reads (g4ref); its yield is LArSoft/lardataalg@03f5e9a2 "
    "lardataalg/DetectorInfo/larproperties.fcl:29-30 (ScintYield 24000, ScintPreScale 0.03)",
}
# name: {run name: record}; the physical run needs no record
REFERENCE_RUNS: dict = {
    "sbnd": {"gdml": SBND_GDML},
    "dune_fd1": {"larsoft": DUNE_LARSOFT},
    "dune_fd1_1x2x6": {"larsoft": DUNE_LARSOFT},
    "dune_fd2": {"larsoft": DUNE_LARSOFT},
}
RUNS_INPUT = {"icarus": "optics"}  # name: the input whose "runs" record holds its reference runs (given by path)


def config(name: str, run: str = PHYSICAL, *, inputs: dict | None = None) -> Run:
    """Return detector ``name``'s run ``run`` (``PHYSICAL``, or a reference run its records name).

    ``inputs``: the detector's input paths, for a detector whose reference runs are in one of them (its
    ``RUNS_INPUT``).
    """
    if run == PHYSICAL:
        return Run()
    records = dict(REFERENCE_RUNS.get(name, {}))
    key = RUNS_INPUT.get(name)
    if key is not None:
        if not inputs or key not in inputs:
            raise ValueError(f"{name!r}: its reference runs are in its input {key!r}: pass inputs={{{key!r}: path}}")
        records.update(json.loads(Path(inputs[key]).read_text()).get("runs", {}))
    if run not in records:
        raise ValueError(f"{name!r}: no run {run!r}; it has {[PHYSICAL, *records]}")
    return Run.of(run, records[run])
