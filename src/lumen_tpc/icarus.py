"""The recipe for ICARUS: its inputs are given by path at conversion; this package holds their sha256 and provenance.

    path = lumen.convert("lumen_tpc:icarus", out="icarus.lumen", data=icarus_dir)   # it holds the three INPUTS files

``recipe(gdml, inputs)`` refuses to build unless every input is there with its expected sha256 (``INPUTS``). The
recipe is LArSoft's legacy optical loader read from the inputs, as MicroBooNE's is from LArSoft's public tables:

- LAr takes LArSoft's tables (``lumen_tpc.larsoft_optics``) and LArSoft's scintillation at its physical yield
  under ICARUS's fcl, from the ``optics`` input's ``lar`` record (``lumen_tpc.larsoft_scintillation``, the one rule
  and record form of every LArSoft experiment); every other material is opaque (no RINDEX).
- Each material of the ``optics`` input's ``surfaces.reflectivity`` gets one skin surface on every LV made of it, of the
  input's type, model, finish and polish, with its REFLECTIVITY table (LArSoft's MaterialPropertyLoader builds these
  in code when SimpleBoundaryProcess is false).
- The sensors are the volOpDetSensitive shells, counted on entry, read by ``lumen:sensor`` with the ``pmt`` input.
- The detector volume is volDetEnclosure, the common mother of both cryostats.
- The ``optics`` input's ``runs`` record holds the LArSoft run's settings, for comparisons only (``lumen_tpc.runs``).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np

from lumen import Recipe, SensorGroup
from lumen.format import schema
from lumen_tpc import inputs as checked
from lumen_tpc import larsoft_optics
from lumen_tpc.larsoft_scintillation import lar_scintillation

LAR = "LAr"
DETECTOR_VOLUME = "volDetEnclosure"
SENSOR_LV = "volOpDetSensitive"

# name: its file name in the directory given, its sha256, where it comes from
INPUTS = {
    "gdml": dict(file="icarus_complete_20220518_overburden.gdml",
                 sha256="6618ab11ed161a6e1ee4434a276fba6a8a467a7a992974f960762821cbb0da9e",
                 source="ICARUS's GDML, SBNSoftware icarusalg geometry, as published"),
    "optics": dict(file="icarus_optics.json",
                   sha256="93ca230224339f723e8962008918634b37734448412bcaaf11c61649a57f92e8",
                   source="ICARUS's LAr scintillation record (lar), ReflectiveSurface tables and LArSoft run settings, "
                   "transcribed from SBNSoftware/icarusalg v10_31_00_02 (692ba35c) "
                   "fcl/services/opticalproperties_icarus.fcl and "
                   "detectorproperties_icarus.fcl, with LArSoft/larsim 0c42311b "
                   "LegacyLArG4/MaterialPropertyLoader.cxx's surface (each value's line in the file)"),
    "pmt": dict(file="icarus_pmt.json",
                sha256="03de5238efa85c580c8c2ce4d94e3509d655c0806e9d71079513eef1cd007604",
                source="ICARUS's PMT value set (lumen-sensor-values/1), its QE from icaruscode "
                "pmtsimulation_icarus.fcl (the tag read is not recorded: unverified)"),
}  # fmt: skip


@dataclasses.dataclass(frozen=True)
class InputRecipe(Recipe):
    """A recipe whose sensor values are one of its inputs: called with the input paths, it checks them (sha256) and
    returns the recipe that reads them; as it stands its group has no model (no value set yet)."""  # noqa: D205, D209

    def __call__(self, gdml, inputs: dict) -> Recipe:
        """Return the recipe for the given input paths, refusing unless each is there with its expected sha256."""
        return recipe(gdml, inputs)


def recipe(gdml, inputs: dict) -> Recipe:
    """Return ICARUS's recipe for the given input paths, refusing unless each is there with its expected sha256."""
    paths = {"gdml": Path(gdml)} | {k: Path(inputs[k]) if k in inputs else Path(gdml).parent / INPUTS[k]["file"]
                                    for k in ("optics", "pmt")}  # fmt: skip
    checked.require({k: (p, INPUTS[k]["sha256"], INPUTS[k]["source"]) for k, p in paths.items()})
    group = SensorGroup("pmt", rule="any_entry", lv=SENSOR_LV, values=str(paths["pmt"]))
    return Recipe(name="icarus", detector_volume=DETECTOR_VOLUME, groups=(group,), decisions=(icarus_optics,),
                  inputs=("optics", "pmt"))  # fmt: skip


def icarus_optics(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """ICARUS's optics as LArSoft's legacy loader gives them to Geant4, from the ``optics`` input (module docstring)."""
    spec = json.loads(Path(inputs["optics"]).read_text())
    s, prov = spec["surfaces"], spec["provenance"]
    lar = df.materials[LAR]
    o = schema.OpticsModel(
        "geant4", settings={}, origin="recipe", note="LArSoft's LAr tables, read as Geant4 reads them"
    )
    props = {**larsoft_optics.lar_tables(), **lar_scintillation("icarus", spec["lar"])}
    mats = {**df.materials, LAR: dataclasses.replace(lar, properties=props, optics=o)}
    e = np.asarray(s["energies_eV"], np.float64)
    surfaces, skins = dict(df.surfaces), list(df.skins)
    for material, values in s["reflectivity"].items():
        lvs = [lv for lv, v in df.volumes.items() if v.material == material]
        if not lvs:
            continue
        name = f"reflector:{material}"
        r = schema.Property(
            "REFLECTIVITY", np.asarray(values, np.float64), energy=e, origin="recipe", note=prov["reflective_surfaces"]
        )
        so = schema.OpticsModel("geant4", settings={}, origin="recipe", note=prov["surface"])
        surfaces[name] = schema.Surface(name, type=s["type"], model=s["model"], finish=s["finish"],
                                        value=float(s["polish"]), properties={"REFLECTIVITY": r},
                                        optics=so)  # fmt: skip
        skins += [
            schema.Skin(f"{name}:{lv}", surface=name, volume=lv, origin="recipe", note=prov["surface"]) for lv in lvs
        ]
    rep = list(df.report) + [f"recipe: LAr from LArSoft's tables; reflector skins on {sorted(s['reflectivity'])} from "
                             "the optics input; every other material opaque"]  # fmt: skip
    return dataclasses.replace(df, materials=mats, surfaces=surfaces, skins=tuple(skins), report=tuple(rep))


ICARUS = InputRecipe(name="icarus", detector_volume=DETECTOR_VOLUME,
                     groups=(SensorGroup("pmt", rule="any_entry", lv=SENSOR_LV),), decisions=(icarus_optics,),
                     inputs=("optics", "pmt"))  # fmt: skip
