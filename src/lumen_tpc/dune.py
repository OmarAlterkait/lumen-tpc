"""Recipes for DUNE: the far detectors FD1 (horizontal drift) and FD2 (vertical drift), and ND-LAr.

The GDMLs are DUNE's public ones, shipped here xz-compressed with their URL, commit and sha256 (``gdml/SOURCES.json``):
dunecore 1861034b dunecore/Geometry/gdml (FD1 dune10kt_v6_refactored_nowires, its 1x2x6 workspace with the wires
dune10kt_v6_refactored_1x2x6, FD2 dunevd10kt_3view_30deg_v6_refactored_nowires) and 2x2_sim 7c621864 geometry (the ND
hall nd_hall_with_lar_tms_sand_TDR_Production_geometry_v_1.0.3). None holds an optical property or surface: LArSoft
gives DUNE its optics at run time, from fcl, and the recipe gives them as LArSoft does:

- dunefd_properties (dunecore larproperties_dune.fcl) is LArSoft's standard_properties (lardataalg larproperties.fcl)
  with ScintYield 24000/MeV, ScintPreScale 0.05, EnableCerenkovLight false and ScintByParticleType true;
  dunefdvd_properties is dunefd_properties. LAr takes LArSoft's tables (``lumen_tpc.larsoft_optics``) and LArSoft's
  scintillation at its physical yield (``lumen_tpc.larsoft_scintillation``: the muon's fast share).
  ScintPreScale and the Cherenkov switch are settings of LArSoft's run, not of the detector: a comparison with
  DUNE's LArSoft output sets them for its run (``lumen_tpc.runs``, run "larsoft").
- detectorproperties.fcl's SimpleBoundaryProcess true (not overridden for DUNE): the stainless steel carries LArSoft's
  reflector, every other material is opaque, as MicroBooNE's (``lumen_tpc.larsoft.microboone_optics``).
- Sensors, counted on entry: FD1's X-ARAPUCA windows (volOpDetSensitive_<i>-<j>-<k>, one LV each), FD2's single and
  double-sided X-ARAPUCAs (volOpDetSensitive, volOpDetSensitiveDouble), ND-LAr's ArCLight tiles (their LAr-side TPB
  layer volTPB_LAr: volArCLight itself is filled by its daughters, so a photon never enters it). Each group is read by
  ``lumen:sensor`` with a published detection efficiency (``sensor_values/dune_*.json``, written by
  ``tools/dune_values.py``), readout ``pe``. No readout gate: DUNE publishes none after emission (duneopdet's
  digitizer window is a triggered waveform window, ReadoutWindow 1000 ticks with PreTrigger 100, within a simulation
  window of minus one drift to the TPC readout's end; duneopdet 303d07d2
  opticaldetectormodules_dune.fcl:28-36); a run gives its own.
- The detector volume: FD1 and FD2 the cryostat's LAr (``auto:argon,lar``); ND-LAr the common mother of its 35
  modules, volArgonCubeDetector75 (the module LV volNDBucket is placed 35 times).
"""

from __future__ import annotations

from lumen import Recipe, SensorGroup
from lumen.format import schema
from lumen_tpc import larsoft


def dune_optics(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """DUNE's optics: LArSoft's standard ones under dunefd_properties (ScintByParticleType true: the muon's share)."""
    return larsoft.standard_optics(df, "dune")


def _group(name: str, pattern: str, values: str) -> SensorGroup:
    return SensorGroup(name, rule="any_entry", lv_pattern=pattern, values=values)


def _recipe(name: str, detector_volume: str, group: SensorGroup) -> Recipe:
    return Recipe(name=name, detector_volume=detector_volume, groups=(group,), decisions=(dune_optics,))


FD1_XARAPUCA = _group("xarapuca", r"^volOpDetSensitive_\d+-\d+-\d+$", "lumen_tpc:dune_fd1_xarapuca")
FD1 = _recipe("dune_fd1", "auto:argon,lar", FD1_XARAPUCA)
FD1_1X2X6 = _recipe("dune_fd1_1x2x6", "auto:argon,lar", FD1_XARAPUCA)
FD2 = _recipe("dune_fd2", "auto:argon,lar",
              _group("xarapuca", r"^volOpDetSensitive(Double)?$", "lumen_tpc:dune_fd2_xarapuca"))  # fmt: skip
NDLAR = _recipe("dune_ndlar", "volArgonCubeDetector75",
                _group("arclight", r"^volTPB_LAr$", "lumen_tpc:dune_ndlar_arclight"))  # fmt: skip
