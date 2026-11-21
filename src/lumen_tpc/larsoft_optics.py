"""Liquid-argon optics from LArSoft's PUBLIC configuration.

The tables are ``data/larsoft_optics_public.json``, written by ``tools/transcribe.py --lardataalg`` from
LArSoft/lardataalg 03f5e9a2 larproperties.fcl: every array with its file:line (only what this package reads: LAr's
RINDEX, RAYLEIGH and ABSLENGTH tables, its ScintYield, and the ReflectiveSurfaces).

    lar_tables()        LAr's RIndexSpectrum, RayleighSpectrum (Babicz et al. 2020, arXiv:2002.09346) and
                        AbsLengthSpectrum as detector-file Property records (RINDEX, RAYLEIGH, ABSLENGTH; energies eV,
                        lengths m, origin "recipe")
                        (read by the default optics model, ``geant4``, as Geant4 reads them: LArSoft hands them to
                        G4OpRayleigh and G4OpAbsorption)
    reflector_tables()  LArSoft's OpBoundaryProcessSimple surface of a named material in its Geant4 form, the
                        properties of a dielectric_metal, unified, ground opticalsurface of sigma_alpha 0:
                        REFLECTIVITY (LArSoft's reflectance), SPECULARSPIKECONSTANT (1 - LArSoft's diffuse share of
                        the reflected light), SPECULARLOBECONSTANT and BACKSCATTERCONSTANT 0, each a table in energy.
                        G4OpBoundaryProcess::DielectricMetal reflects with probability R, then spike, lobe,
                        backscatter, else Lambertian (the diffuse share); at sigma_alpha 0 the lobe would be the
                        spike: LArSoft's specular-or-Lambertian reflection about the global normal, read by the
                        default optics model (``geant4``) as Geant4 reads it

Only the public tables live here; the readings are lumen's general rules.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from lumen.format import schema
from lumen.units import LENGTH_M, exact

DATA = Path(__file__).parent / "data" / "larsoft_optics_public.json"
STANDARD = "larsoft_standard"
LENGTH_UNITS = {u: LENGTH_M[u] for u in ("cm",)}  # the length units the tables are given in: m per unit, exact
REFLECTIVITY, SPIKE, LOBE, BACK = "REFLECTIVITY", "SPECULARSPIKECONSTANT", "SPECULARLOBECONSTANT", "BACKSCATTERCONSTANT"


@lru_cache(maxsize=1)
def data() -> dict:
    """Return the shipped LArSoft optics tables."""
    return json.loads(DATA.read_text())


def _sorted_table(entry, factor: str | None = None):
    """Return (energies ascending, values) of a {energy (eV), values} entry.

    ``factor``: the decimal m per unit of a length table, applied exactly (one rounding), as the GDML importer converts
    a literal (``lumen.units``).
    """
    e = np.asarray(entry["energy"], np.float64)
    vals = [float(x) for x in entry["values"]]
    v = np.asarray([exact(repr(x), factor) for x in vals] if factor else vals, np.float64)
    o = np.argsort(e, kind="stable")
    return e[o], v[o]


def _length_scale(entry, key):
    unit = entry.get("value_unit", "cm")
    if unit not in LENGTH_UNITS:
        raise ValueError(f"LArSoft table {key}: length unit {unit!r} is not one of {sorted(LENGTH_UNITS)}")
    return LENGTH_UNITS[unit]


def lar_tables() -> dict[str, schema.Property]:
    """Return LAr's LArSoft tables as Property records {RINDEX, RAYLEIGH, ABSLENGTH} (energies eV, lengths m)."""
    d = data()["lar"][STANDARD]
    out = {}
    for key, name, length in (("RINDEX", "rindex", False), ("RAYLEIGH", "rayleigh_length", True),
                              ("ABSLENGTH", "abs_length", True)):  # fmt: skip
        entry = d[name]
        e, v = _sorted_table(entry, _length_scale(entry, name) if length else None)
        note = f"LArSoft {STANDARD} {name}: {entry.get('source', d['source'])}"
        out[key] = schema.Property(key, v, energy=e, origin="recipe", note=note)
    return out


def reflector_tables(material: str) -> dict[str, schema.Property]:
    """Return LArSoft's ReflectiveSurface of a material in its Geant4 form (see the module docstring): the tables
    {REFLECTIVITY, SPECULARSPIKECONSTANT, SPECULARLOBECONSTANT, BACKSCATTERCONSTANT} as Property records."""  # noqa: D205, D209
    s = data()["surfaces"][STANDARD]
    e = np.asarray(s["energies_eV"], np.float64)
    m = s["surfaces"][material]
    note = f"LArSoft {STANDARD} ReflectiveSurfaces {material}: {s['source']}"
    spike = 1.0 - np.asarray(m["diffuse_fraction"], np.float64)

    def table(key, value, how=""):
        return schema.Property(key, np.asarray(value, np.float64), energy=e, origin="recipe", note=note + how)

    return {REFLECTIVITY: table(REFLECTIVITY, m["reflectance"]),
            SPIKE: table(SPIKE, spike, "; 1 - its diffuse fraction"),
            LOBE: table(LOBE, np.zeros_like(e), "; no lobe (LArSoft: specular or Lambertian)"),
            BACK: table(BACK, np.zeros_like(e), "; no backscatter")}  # fmt: skip
