"""Recipes for the LArSoft detectors: SBND (its full-simulation GDML) and MicroBooNE (LArSoft's public optics).

SBND (sbnd_v02_00_full_simulation.gdml, sbndcode 4e41b3d8): the GDML holds every optical property SBND's full
optical simulation gives Geant4. The recipe's decisions, each checked against the GDML first:

- The TPB film (volCPATPB, 23 nm on one face of each CPA foil volCPAFoil, vm2000 50.8 um) is thinner than the band
  lumen's navigator resolves, and lumen lowers no film onto a surface: the recipe splits the foil into a front half of
  TPB (25.4 um, on the film's side, bulk WLS with TPB's own tables) and a back half of vm2000 that keeps the foil's
  Surface_vm2000 skin; the 23 nm box is dropped (``sbnd_cpa_tpb``). It is G4OpWLS's law on the film: TPB absorbs the
  VUV within ~1e-14 m, is index-matched to LAr and nearly transparent to its own light (d/L ~2.5e-7), and re-emits at
  once (WLSTIMECONSTANT 0); the differences from the 23 nm volume are <= 0.2 ps of flight, ~50 um x tan(theta)
  laterally and ~1e-4 of side-face entries.
- The outside: the detector volume (volCryostat) fills the hole of volCryoMembrane (steel); the general outside rule
  (``lumen.rules.binding.outside_volume``) gives the outside the membrane's skin, as Geant4 does.
- The sensors are the volumes with the SensDet aux value PhotonDetector: 120 PMTs (volOpDetSensitive) and 192
  X-ARAPUCA windows (volOpDetSensitiveXArapucaFilter), counted on entry; their physvol copy number is the OpDet channel,
  typed by sbndcode's sbnd_pds_mapping.json (input ``pds_mapping``). One sensor group per type (the id map's column
  ``type``), each read by ``lumen:sensor`` with that type's sbndcode values: pmt_coated (96), pmt_uncoated (24),
  xarapuca_vuv (96), xarapuca_vis (96).
- LAr's scintillation is what sbndcode's LArSoft gives Geant4 (LArSoft's MaterialPropertyLoader replaces the GDML's):
  lardataalg's standard_properties under sbndcode's opticalproperties_sbnd.fcl (ScintSlowTimeConst 1300 ns,
  ScintByParticleType true: the muon's fast share, 0.23), at the physical ScintYield (``larsoft_scintillation``). The
  GDML's SCINTILLATIONYIELD is ScintYield x ScintPreScale (the prescale stands in for the detection efficiency in
  LArSoft, which the sensor models here apply instead) and its YIELDRATIO 0.27 is not what LArSoft uses.

MicroBooNE (microboone.gdml, which holds no optical property): only LAr carries optical properties in LArSoft's
MicroBooNE simulation (LArSoft's tables, ``lumen_tpc.larsoft_optics``, and its scintillation as standard_properties
gives it: the physical ScintYield, the fast share ScintYieldRatio, ``lumen_tpc.larsoft_scintillation``; uboone/ubevt
larproperties_microboone.fcl: microboone_properties is standard_properties); every other material has no RINDEX in the
GDML, so it kills a photon at its boundary, except the stainless steel, which carries LArSoft's reflector in its Geant4
form (a dielectric_metal, unified, ground surface of sigma_alpha 0, its spike 1 - LArSoft's diffuse fraction:
``larsoft_optics.reflector_tables``). Photons are counted on entering the volOpDetSensitive discs. The tables keep their
source tokens (the numbers in eV and cm, as LArSoft hands them to Geant4), so a GDML export makes Geant4 read the
doubles LArSoft's Geant4 reads."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from lumen import Recipe, SensorGroup
from lumen.format import schema
from lumen_tpc.larsoft_scintillation import experiment

LAR = "LAr"
SCINTILLATIONYIELD = "SCINTILLATIONYIELD"


def channel_of(df: schema.DetectorFile, mother_lv: str, child_lv: str) -> int:
    """Return the copy number of the one physvol of ``child_lv`` inside ``mother_lv`` (an OpDet channel)."""
    hits = [p.copy for p in _daughters_all(df, mother_lv) if p.volume == child_lv]
    if len(hits) != 1:
        raise ValueError(f"{mother_lv!r}: {len(hits)} placements of {child_lv!r} (want 1)")
    return hits[0]


def _daughters_all(df, lv):
    return [df.placements[i] for i in df.volumes[lv].daughters]


def placement_chain(df: schema.DetectorFile, path: str) -> list:
    """Return the detector file's placements along a sensor's path (its physvol names from the top, then its LV).

    A path starts at the detector volume: its first physvol is a placement of the detector volume of that name (the
    detector volume may be placed in more than one mother; its daughters are the same); each next one is the daughter
    of that name of the volume the last placed.
    """
    *names, lv = str(path).split("/")
    first = [p for p in df.placements if p.name == names[0] and p.volume == df.detector_volume]
    if not first:
        raise ValueError(f"{path!r}: no physvol {names[0]!r} places the detector volume {df.detector_volume!r}")
    chain = first[:1]
    for name in names[1:]:
        step = [p for p in _daughters_all(df, chain[-1].volume) if p.name == name]
        if len(step) != 1:
            raise ValueError(f"{path!r}: {len(step)} physvols named {name!r} in {chain[-1].volume!r} (want 1)")
        chain.append(step[0])
    if chain[-1].volume != lv:
        raise ValueError(f"{path!r}: its last physvol places {chain[-1].volume!r}, not {lv!r}")
    return chain


def sbnd_columns(df, paths, inputs) -> dict:
    """Return the id map's per-sensor OpDet channel, type and logical volume."""
    types = {int(r["channel"]): r["pd_type"] for r in json.loads(Path(inputs["pds_mapping"]).read_text())}
    ch, ty, lv = [], [], []
    for path in paths:
        mother, sensor = placement_chain(df, path)[-2:]
        c = channel_of(df, mother.volume, sensor.volume)
        ch.append(c)
        ty.append(types[c])
        lv.append(sensor.volume)
    if len(set(ch)) != len(ch):
        raise ValueError("sbnd: OpDet channels are not unique")
    return {"channel": ch, "type": ty, "lv": lv}


def sbnd_scintillation(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """LAr's scintillation as sbndcode gives it to Geant4: standard_properties under opticalproperties_sbnd.fcl
    (``larsoft_scintillation.lar_scintillation("sbnd")``), in place of the GDML's."""  # noqa: D205, D209
    from lumen.rules.keys import G4_10_KEYS
    from lumen_tpc.larsoft_scintillation import lar_scintillation

    lar = df.materials[LAR]
    if SCINTILLATIONYIELD not in lar.properties:
        raise ValueError(f"sbnd: {LAR} has no {SCINTILLATIONYIELD} in the GDML")
    old = sorted(k for k in lar.properties if k.startswith("SCINTILLATION") or k in G4_10_KEYS)  # Geant4 10's too
    props = {k: v for k, v in lar.properties.items() if k not in old} | lar_scintillation("sbnd")
    mats = {**df.materials, LAR: dataclasses.replace(lar, properties=props)}
    rep = list(df.report) + [f"recipe: {LAR} scintillates as sbndcode's LArSoft (standard_properties under "
                             f"opticalproperties_sbnd.fcl: the physical yield, the muon's fast share); the GDML's "
                             f"{old} replaced"]  # fmt: skip
    return dataclasses.replace(df, materials=mats, report=tuple(rep))


CPA_FOIL, CPA_TPB, TPB = "volCPAFoil", "volCPATPB", "TPB"
CPA_FRONT = "volCPAFoilTPB"  # the foil's front half, of TPB


def _box_placement(df, lv):
    """Return (index, placement) of the one placement of box volume ``lv``, unturned in its mother."""
    pls = [(i, p) for i, p in enumerate(df.placements) if p.volume == lv]
    if len(pls) != 1 or df.solids[df.volumes[lv].solid].type != "box" or any(abs(a) > 0 for a in pls[0][1].rotation):
        raise ValueError(f"sbnd: {lv!r} is not one unturned box placement ({len(pls)} placements)")
    return pls[0]


def sbnd_cpa_tpb(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """Split the CPA foil (vm2000) into a front half of TPB on the film's side and a back half of vm2000 keeping the
    foil's skin; drop the 23 nm TPB box (the module docstring)."""  # noqa: D205, D209
    import numpy as np

    (i_f, foil), (i_t, film) = _box_placement(df, CPA_FOIL), _box_placement(df, CPA_TPB)
    if foil.mother != film.mother:
        raise ValueError(f"sbnd: {CPA_FOIL!r} and {CPA_TPB!r} are not placed in one volume")
    box = df.solids[df.volumes[CPA_FOIL].solid]
    dims = np.array([box.params[k] for k in "xyz"], np.float64)
    k = int(np.argmin(dims))  # the foil's thin axis
    side = float(np.sign(film.position[k] - foil.position[k]))  # the film's side of the foil
    half = dims[k] / 2
    name = f"{box.name}Half"
    hbox = dataclasses.replace(box, name=name, params={**box.params, "xyz"[k]: float(half)})

    def moved(p, sign, **kw):
        pos = list(p.position)
        pos[k] = float(foil.position[k] + sign * side * half / 2)
        return dataclasses.replace(p, position=tuple(pos), **kw)

    placements = list(df.placements)
    placements[i_f] = moved(foil, -1.0)
    placements[i_t] = moved(film, 1.0, name=f"{CPA_FRONT}_PV", volume=CPA_FRONT)
    volumes = {n: v for n, v in df.volumes.items() if n != CPA_TPB}
    volumes[CPA_FOIL] = dataclasses.replace(df.volumes[CPA_FOIL], solid=name)
    volumes[CPA_FRONT] = schema.Volume(CPA_FRONT, name, TPB)
    film_solid = df.volumes[CPA_TPB].solid
    d_film = df.solids[film_solid].params["xyz"[k]]
    used = {v.solid for v in volumes.values()}
    solids = {n: s for n, s in df.solids.items() if n != film_solid or n in used} | {name: hbox}
    rep = list(df.report) + [f"recipe: {CPA_FOIL} ({df.volumes[CPA_FOIL].material}, {dims[k] * 1e6:.1f} um) split "
                             f"into {CPA_FRONT} ({TPB}, {half * 1e6:.1f} um, on {CPA_TPB}'s side: bulk WLS) and its "
                             f"back half keeping its skin; {CPA_TPB} ({d_film * 1e9:.0f} nm) dropped"]  # fmt: skip
    return dataclasses.replace(df, solids=solids, volumes=volumes, placements=tuple(placements), report=tuple(rep))


# SBND's readout gate, ns after emission: five of LAr's slow scintillation time constants, read from the record SBND's
# scintillation is (sbndcode's opticalproperties_sbnd.fcl ScintSlowTimeConst, 1300 ns: 6500 ns), all but e^-5 = 0.7 %
# of the slow light, which also holds the TPB re-emission delay and the crossing of the detector (tens of ns)
GATE_SLOW_TIME_CONSTANTS = 5
SBND_GATE = (0.0, GATE_SLOW_TIME_CONSTANTS * float(experiment("sbnd")["slow_time_constant"]["value"]))


def _sbnd_group(pd_type: str, lv: str, values: str) -> SensorGroup:
    return SensorGroup(pd_type, rule="any_entry", lv=lv, values=values, where={"type": pd_type},
                       readout={"gate": SBND_GATE})  # fmt: skip


# Neither SBND's nor MicroBooNE's GDML has a defect Geant4 refuses: both are converted as published.
SBND = Recipe(
    name="sbnd", detector_volume="auto:argon,lar",
    groups=(_sbnd_group("pmt_coated", "volOpDetSensitive", "lumen_tpc:sbnd_pmt"),
            _sbnd_group("pmt_uncoated", "volOpDetSensitive", "lumen_tpc:sbnd_pmt_uncoated"),
            _sbnd_group("xarapuca_vuv", "volOpDetSensitiveXArapucaFilter", "lumen_tpc:sbnd_xarapuca_vuv"),
            _sbnd_group("xarapuca_vis", "volOpDetSensitiveXArapucaFilter", "lumen_tpc:sbnd_xarapuca_vis")),
    decisions=(sbnd_scintillation, sbnd_cpa_tpb), inputs=("pds_mapping",), sensor_columns=sbnd_columns)  # fmt: skip


# ------------------------------------------------------------------------------------------------------- MicroBooNE
STEEL = "STEEL_STAINLESS_Fe7Cr2Ni"
STEEL_SURFACE = "steel"


def standard_optics(df: schema.DetectorFile, experiment: str) -> schema.DetectorFile:
    """LArSoft's standard optics: LAr's tables and its scintillation under ``experiment``'s fcl
    (``larsoft_scintillation.lar_scintillation(experiment)``) and the steel reflector; every other material opaque."""  # noqa: D205, D209
    from lumen_tpc import larsoft_optics, larsoft_scintillation
    from lumen_tpc.larsoft_scintillation import lar_scintillation

    o = schema.OpticsModel(
        "geant4", settings={}, origin="recipe", note="LArSoft's LAr tables, read as Geant4 reads them"
    )
    props = {**larsoft_optics.lar_tables(), **lar_scintillation(experiment)}
    mats = {**df.materials, LAR: dataclasses.replace(df.materials[LAR], properties=props, optics=o)}
    o = schema.OpticsModel(
        "geant4", settings={}, origin="recipe", note="LArSoft's ReflectiveSurfaces in their Geant4 form"
    )
    steel = schema.Surface(STEEL_SURFACE, type="dielectric_metal", model="unified", finish="ground", value=0.0,
                           properties=larsoft_optics.reflector_tables(STEEL), optics=o)  # fmt: skip
    skins = tuple(schema.Skin(f"steel:{lv}", surface=STEEL_SURFACE, volume=lv, origin="recipe",
                              note="LArSoft's steel reflector")
                  for lv, v in df.volumes.items() if v.material == STEEL)  # fmt: skip
    by_particle = larsoft_scintillation.experiment(experiment)["by_particle_type"]["value"]
    share = f"{larsoft_scintillation.PARTICLE}ScintYieldRatio" if by_particle else "ScintYieldRatio"
    rep = list(df.report) + [f"recipe: LAr from LArSoft's tables and scintillation (the physical yield, the fast "
                             f"share {share}); the steel carries LArSoft's reflector; every other material is "
                             "opaque"]  # fmt: skip
    return dataclasses.replace(
        df, materials=mats, surfaces={**df.surfaces, STEEL_SURFACE: steel}, skins=skins, report=tuple(rep)
    )


def microboone_optics(df: schema.DetectorFile, inputs: dict) -> schema.DetectorFile:
    """MicroBooNE's optics: LArSoft's standard ones under its fcl (microboone_properties is standard_properties,
    ScintByParticleType false: the fast share ScintYieldRatio)."""  # noqa: D205, D209
    return standard_optics(df, "microboone")


MICROBOONE = Recipe(
    name="microboone", detector_volume="auto:argon,lar",
    groups=(SensorGroup("pmt", rule="any_entry", lv="volOpDetSensitive", values="lumen_tpc:microboone_qe"),),
    decisions=(microboone_optics,))  # fmt: skip
