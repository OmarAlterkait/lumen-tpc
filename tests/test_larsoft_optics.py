"""LArSoft's public optics (lumen_tpc.larsoft_optics; moved from lumen): the tables as detector-file Property
records give LArSoft's LAr medium and steel reflector exactly."""

from decimal import Decimal

import numpy as np

from lumen.format import schema
from lumen.media import bulk, phase
from lumen.rules import optics as rules
from lumen.units import HC
from lumen_tpc import larsoft_optics as lar

STEEL = "STEEL_STAINLESS_Fe7Cr2Ni"


def test_tables_are_property_records_in_detector_file_units():
    d = lar.data()["lar"]["larsoft_standard"]
    t = lar.lar_tables()
    assert set(t) == {"RINDEX", "RAYLEIGH", "ABSLENGTH"} and all(p.origin == "recipe" for p in t.values())
    assert np.array_equal(t["RINDEX"].energy, d["rindex"]["energy"]) and np.all(np.diff(t["RAYLEIGH"].energy) > 0)
    for key, name in (("RAYLEIGH", "rayleigh_length"), ("ABSLENGTH", "abs_length")):  # cm -> m, exact decimals
        want = np.array([float(Decimal(repr(float(v))) * Decimal("0.01")) for v in d[name]["values"]])
        assert np.array_equal(t[key].value, want[np.argsort(d[name]["energy"], kind="stable")])


def test_lar_tables_are_read_by_geant4():
    rec = schema.Material(
        name="LAr", state="liquid", composition=schema.Composition(density_g_cm3=1.39), properties=lar.lar_tables()
    )
    e = rules.medium(rec, "lar")
    m, p = e.medium, e.params
    assert m.name == "lar" and m.index.form == "g4_rindex"
    assert [c.name for c in m.channels] == ["rayleigh"] and m.channels[0].lobe is phase.RAYLEIGH
    t = lar.lar_tables()
    for k, key in (("index", "RINDEX"), ("absorption", "ABSLENGTH")):
        assert p[k]["value"].tobytes() == t[key].value.tobytes()
    assert p["rayleigh"]["length"]["value"].tobytes() == t["RAYLEIGH"].value.tobytes()
    bulk.validate(m, p)
    # the index is Geant4's: n at 128 nm is the table linear in energy
    n = float(m.index({"energy": p["index"]["energy"], "value": p["index"]["value"]}, np.float32(128.0)))
    assert abs(n - np.interp(HC / 128.0, p["index"]["energy"], p["index"]["value"])) < 1e-5


def test_the_reflector_is_written_in_its_geant4_form():
    """LArSoft's steel: REFLECTIVITY its reflectance, SPECULARSPIKECONSTANT 1 - its diffuse fraction, no lobe and no
    backscatter, on the tables' energies; the recipe writes it as a geant4 dielectric_metal, unified, ground surface of
    sigma_alpha 0 (the spike, as LArSoft reflects: specular or Lambertian about the global normal)."""
    from lumen_tpc import larsoft

    props = lar.reflector_tables(STEEL)
    raw = lar.data()["surfaces"]["larsoft_standard"]["surfaces"][STEEL]
    assert set(props) == {"REFLECTIVITY", "SPECULARSPIKECONSTANT", "SPECULARLOBECONSTANT", "BACKSCATTERCONSTANT"}
    assert np.array_equal(props["REFLECTIVITY"].value, raw["reflectance"])
    assert np.array_equal(props["SPECULARSPIKECONSTANT"].value, 1.0 - np.asarray(raw["diffuse_fraction"]))
    assert not props["SPECULARLOBECONSTANT"].value.any() and not props["BACKSCATTERCONSTANT"].value.any()
    lar_ = schema.Material(name="LAr", state="liquid", composition=schema.Composition(density_g_cm3=1.39))
    df = schema.DetectorFile(name="t", world="LV", detector_volume="LV", solids={},
                             volumes={"LV": schema.Volume(name="LV", solid="s", material=STEEL)}, placements=(),
                             materials={larsoft.LAR: lar_})  # fmt: skip
    steel = larsoft.microboone_optics(df, {}).surfaces[larsoft.STEEL_SURFACE]
    assert (steel.type, steel.model, steel.finish, steel.value, steel.optics.name) == (
        "dielectric_metal",
        "unified",
        "ground",
        0.0,
        "geant4",
    )
