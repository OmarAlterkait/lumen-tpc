"""LAr scintillation as each LArSoft experiment gives it to Geant4 (``data/larsoft_optics_public.json``), in Geant4 11
keys.

    lar_scintillation("sbnd")   {SCINTILLATIONYIELD, SCINTILLATIONCOMPONENT1/2, SCINTILLATIONTIMECONSTANT1/2,
                                 SCINTILLATIONYIELD1/2} as detector-file Property records (origin "recipe"):
                                 lardataalg's standard_properties under the experiment's own fcl (``lar.<experiment>``
                                 of the tables, one record per experiment: dune, microboone, sbnd), each value with
                                 its file and line
    lar_scintillation(name, record)   the same from a record an input gives ({"overrides": {...}}: a detector whose
                                      inputs are given by path holds its record there)

One rule for every experiment: its fcl's ScintByParticleType decides the yield and the fast share. False: ScintYield
and ScintYieldRatio. True: the muon's (MuonScintYield, MuonScintYieldRatio): LArSoft's share is per particle, a
material holds one, and the muon's is the one every ScintByParticleType experiment here reads for its tracks
(``PARTICLE``).

The yield is LArSoft's physical ScintYield (photons/MeV); ScintPreScale, which LArSoft multiplies in before Geant4 and
divides out of its detection efficiency later, is a run setting of its simulation, not the detector's light: it is
not here (a comparison with such a run sets it for the run, ``lumen_tpc.runs``). LArSoft's MaterialPropertyLoader
gives Geant4 the fast share as YIELDRATIO (Geant4 10), which Geant4 11 splits into SCINTILLATIONYIELD1 and 2: the
share and the rest.
"""

from __future__ import annotations

import copy

import numpy as np

from lumen.format import schema
from lumen_tpc import larsoft_optics

PARTICLE = "Muon"  # the particle whose share a material holds when ScintByParticleType is true


def experiment(name: str, record: dict | None = None) -> dict:
    """Return standard_properties' scintillation entries under experiment ``name``'s fcl overrides (``lar.<name>`` of
    the tables, or ``record``)."""  # noqa: D205, D209
    lar = larsoft_optics.data()["lar"]
    if record is None:
        if name not in lar or name == larsoft_optics.STANDARD:
            raise ValueError(f"lar_scintillation: no LArSoft experiment {name!r} in the tables")
        record = lar[name]
    d = copy.deepcopy(lar[larsoft_optics.STANDARD])
    for entry, o in record["overrides"].items():
        if entry.startswith("per_particle."):
            _, particle, field = entry.split(".")
            pp = d["per_particle"][particle]
            pp[field] = o["value"]
            pp.setdefault("sources", {})[field] = o["source"]
        else:
            d[entry] = o
    return d


def lar_scintillation(name: str, record: dict | None = None) -> dict[str, schema.Property]:
    """Return LAr's scintillation keys as experiment ``name``'s LArSoft gives them (module docstring)."""
    d = experiment(name, record)

    def const(key, value, note, source):
        return schema.Property(
            key, np.asarray(float(value), np.float64), energy=None, origin="recipe", note=f"LArSoft {note}: {source}"
        )

    out = {}
    for i, entry in ((1, "fast_scint_spectrum"), (2, "slow_scint_spectrum")):
        e = np.asarray(d[entry]["energy"], np.float64)
        v = np.asarray(d[entry]["values"], np.float64)
        o = np.argsort(e, kind="stable")
        note = f"LArSoft {entry}: {d[entry]['source']}"
        out[f"SCINTILLATIONCOMPONENT{i}"] = schema.Property(f"SCINTILLATIONCOMPONENT{i}", v[o], energy=e[o],
                                                            origin="recipe", note=note)  # fmt: skip
    for i, entry in ((1, "fast_time_constant"), (2, "slow_time_constant")):
        out[f"SCINTILLATIONTIMECONSTANT{i}"] = const(f"SCINTILLATIONTIMECONSTANT{i}", d[entry]["value"],
                                                     f"{entry} (ns)", d[entry]["source"])  # fmt: skip
    if not d["by_particle_type"]["value"]:
        y, ys = d["scint_yield"]["value"], d["scint_yield"]["source"]
        fast, fs, fn = d["yield_ratio"]["value"], d["yield_ratio"]["source"], "ScintYieldRatio"
    else:
        pp = d["per_particle"][PARTICLE]
        over = pp.get("sources", {})
        y, fast = pp["yield_per_MeV"], pp["fast_fraction"]
        ys, fs = over.get("yield_per_MeV", pp["source"]), over.get("fast_fraction", pp["source"])
        fn = f"{PARTICLE}ScintYieldRatio"
    out["SCINTILLATIONYIELD"] = const("SCINTILLATIONYIELD", y, "physical yield (/MeV)", ys)
    out["SCINTILLATIONYIELD1"] = const("SCINTILLATIONYIELD1", fast, f"{fn} (the fast share)", fs)
    out["SCINTILLATIONYIELD2"] = const("SCINTILLATIONYIELD2", 1.0 - float(fast), f"1 - {fn}", fs)
    return out
