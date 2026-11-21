"""lumen-tpc's recipes, value sets and references: each value set loads with its provenance and holds sbndcode's
numbers; SBND's recipe reads each sensor type and LArSoft's physical yield; each timed group has its readout gate; the
g4ref references gate. (Moved from lumen's unit tests.)"""

from pathlib import Path

import jax.numpy as jnp
import numpy as np
import pytest

from lumen import readout as rd
from lumen import testing
from lumen.compare import references
from lumen.format import schema
from lumen.units import wavelength_of
from lumen_tpc import DETECTORS, REFERENCES, larsoft

SETS = ("sbnd_pmt", "sbnd_pmt_uncoated", "microboone_qe", "sbnd_xarapuca_vuv", "sbnd_xarapuca_vis")


def _load(name):
    return testing.load_value_set(f"lumen_tpc:{name}")


def _hist(m, n=400, n_sensors=3, gate=(0.0, 120.0), t0=20.0, seed=0):
    """A histogram of a photon list: random sensors, wavelengths in 320-580 nm, crossing points at cathode angles in
    0-80 deg (on the unit sphere about the sensor's axis), times t0."""
    rng = np.random.default_rng(seed)
    a = np.radians(rng.uniform(0.0, 80.0, n))
    ph = dict(sensor=rng.integers(0, n_sensors, n), lam=rng.uniform(320.0, 580.0, n),
              pos=np.stack([np.sin(a), np.zeros(n), np.cos(a)], -1), time=t0 + 0.0 * rng.standard_normal(n),
              weight=rng.uniform(0.5, 1.5, n))  # fmt: skip
    return testing.histograms(m, gate, n_sensors, ph, group="pmt")


GDML = """<?xml version="1.0" encoding="UTF-8" ?>
<gdml>
<define>
  <constant name="HALF" value="0.5"/>
  <position name="p1" unit="cm" x="1.25" y="0" z="HALF*2"/>
  <rotation name="r1" unit="deg" x="90" y="0" z="0"/>
  <matrix name="RIX0x1" coldim="2" values="2.0*eV 1.33 3.0*eV 1.34 4.5e-06 1.35"/>
  <matrix name="ABS0x2" coldim="2" values="2.0*eV 1000.0 4.5*eV 20*m"/>
  <matrix name="REF" coldim="2" values="2.0*eV 0.9 4.5*eV 0.8"/>
  <matrix name="GV" coldim="2" values="2.0*eV 220 4.5*eV 1e30"/>
</define>
<materials>
  <element name="H" formula="H" Z="1"> <atom value="1.008"/> </element>
  <element name="O" formula="O" Z="8"> <atom value="15.999"/> </element>
  <material name="Water" state="liquid">
    <property name="RINDEX" ref="RIX0x1"/>
    <property name="ABSLENGTH" ref="ABS0x2"/>
    <D value="1.0" unit="g/cm3"/>
    <composite n="2" ref="H"/> <composite n="1" ref="O"/>
  </material>
  <material name="Steel" state="solid"> <D value="7.9"/> <fraction n="1.0" ref="O"/> </material>
</materials>
<solids>
  <box name="World" x="4" y="4" z="4" lunit="m"/>
  <box name="Tank" x="2000" y="2000" z="2000" lunit="mm"/>
  <tube name="Pmt" rmax="12.5" z="10" deltaphi="360" aunit="deg" lunit="cm"/>
  <opticalsurface name="Liner" model="unified" finish="ground" type="dielectric_metal" value="0.1">
    <property name="REFLECTIVITY" ref="REF"/>
    <property name="GROUPVEL" ref="GV"/>
  </opticalsurface>
</solids>
<structure>
  <volume name="PmtLV"> <materialref ref="Steel"/> <solidref ref="Pmt"/> </volume>
  <volume name="TankLV"> <materialref ref="Water"/> <solidref ref="Tank"/>
    <physvol name="pmt0x10"> <volumeref ref="PmtLV"/> <positionref ref="p1"/> <rotationref ref="r1"/> </physvol>
    <physvol name="pmt0x20" copynumber="2"> <volumeref ref="PmtLV"/> <position name="q" x="-500" y="0" z="0"/>
    </physvol>
  </volume>
  <volume name="WorldLV"> <materialref ref="Water"/> <solidref ref="World"/>
    <physvol name="tank"> <volumeref ref="TankLV"/> </physvol>
    <auxiliary auxtype="Region" auxvalue="R"> <auxiliary auxtype="cut" auxvalue="1" auxunit="mm"/> </auxiliary>
  </volume>
  <skinsurface name="LinerSkin" surfaceproperty="Liner"> <volumeref ref="TankLV"/> </skinsurface>
  <bordersurface name="B1" surfaceproperty="Liner"> <physvolref ref="tank"/> <physvolref ref="pmt0x10"/>
  </bordersurface>
</structure>
<setup name="Default" version="1.0"> <world ref="WorldLV"/> </setup>
</gdml>
"""


def write(tmp_path, text, name="toy.gdml"):
    p = tmp_path / name
    p.write_text(text)
    return p


def _split_edge():
    """The band edge (nm) at the split energy the SBND reference runs used (the manifest's split_ev)."""
    return (wavelength_of(references.spec("charge", "sbnd", (REFERENCES,))["split_ev"]),)


def test_the_g4ref_runs_split_at_the_manifest_s_energy():
    """SBND's and MicroBooNE's g4ref runs (the manifest's producers' run blocks), on the original GDML and on the
    export, split the light at the manifest's split_ev (larsim's PhotonHitConverter energy), the energy the value
    sets' band edge and the charge check read."""
    import json

    split = references.spec("charge", "sbnd", (REFERENCES,))["split_ev"]
    products = json.loads(Path(REFERENCES).read_text())["products"]
    runs = {k: e["producer"] for k, e in products.items() if "run" in (e.get("producer") or {})}
    flags = {k: p["run"].get("flags", p.get("flags", [])) for k, p in runs.items()}
    assert set(flags) == {"sbnd-g4ref-original", "microboone-g4ref-original", "sbnd-g4ref-export",
                          "microboone-g4ref-export"}, flags  # fmt: skip
    assert all(float(f[f.index("--split-ev") + 1]) == split for f in flags.values()), flags


def _band_edges(m):
    """The edges between a value set's QE bands (nm): its wavelength axis's, without the open end bands' infinities."""
    return m.axis("wavelength").edges[1:-1]


def _numbered(d):
    """The value set's fields a source or a choice must account for: every non-null top-level field, and each
    numeric field of the front end."""
    skip = {"schema", "model", "name", "readout", "provenance", "frontend"}
    out = {k for k, v in d.items() if k not in skip and v is not None}
    return out | {f"frontend/{k}" for k, v in d["frontend"].items() if not isinstance(v, str)}


@pytest.mark.parametrize("name", SETS)
def test_every_number_has_a_source_or_is_a_stated_choice(name):
    """Each field is either transcribed (provenance.fields: file:line) or a stated choice of this package
    (provenance.choices: the value and its reason), never both and never neither."""
    import json
    from importlib import resources

    d = json.loads((resources.files("lumen_tpc") / "sensor_values" / f"{name}.json").read_text())
    fields, choices = d["provenance"]["fields"], d["provenance"]["choices"]
    assert not set(fields) & set(choices)
    assert _numbered(d) <= set(fields) | set(choices), _numbered(d) - set(fields) - set(choices)


@pytest.mark.parametrize("name", SETS)
def test_shipped_set_loads_with_provenance(name):
    testing.check_value_set(f"lumen_tpc:{name}")


def test_sbnd_pulse_is_the_ideal_spe():
    """sbnd_pmt's pulse: the fcl's 10-90 % rise and fall times about the 55.1 ns transit time."""
    m = _load("sbnd_pmt")
    t = jnp.linspace(40.0, 100.0, 60001)
    h = np.asarray(m.pulse.shape({k: jnp.asarray(m.values[f"pulse/{k}"]) for k in m.pulse.fields()}, t))
    tt = np.asarray(t)
    rise = tt[(h >= 0.9) & (tt < 55.1)].min() - tt[(h >= 0.1) & (tt < 55.1)].min()
    fall = tt[(h >= 0.1) & (tt > 55.1)].max() - tt[(h >= 0.9) & (tt > 55.1)].max()
    np.testing.assert_allclose([rise, fall], [3.8, 13.7], atol=2e-3)


def test_sbnd_pmt_qe_is_sbndcode_s_two_numbers():
    """The SBND PMTs: sbndcode's two efficiencies per real photon split at larsim's PhotonHitConverter energy (the
    reference runs' split), as the X-ARAPUCA sets: on a coated tube the VUV and the visible one, on an uncoated tube
    none below the edge and its one number above. Per real photon: sbndcode divides them by ScintPreScale."""
    coated, bare = _load("sbnd_pmt"), _load("sbnd_pmt_uncoated")
    assert coated.values["qe"].tolist() == [0.0392, 0.026] and bare.values["qe"].tolist() == [0.0, 0.0357]
    assert _band_edges(coated) == _band_edges(bare) == _split_edge()
    assert "digi_pmt_sbnd.fcl:38" in coated.provenance["fields"]["qe"]
    assert "digi_pmt_sbnd.fcl:40" in bare.provenance["fields"]["qe"]
    assert all("PhotonHitConverter_module.cc" in m.provenance["fields"]["qe"] for m in (coated, bare))
    assert all("ScintPreScale" in m.provenance["fields"]["qe"] for m in (coated, bare))


def test_sbnd_xarapuca_sets_are_sbndcode_s():
    """The X-ARAPUCA sets: sbndcode's efficiencies per real photon split at that energy (a visible one reads no VUV),
    the VUV box's time table, and the visible bar's 8.5 ns decay followed by the TPB time; their time grids hold."""
    vuv, vis = _load("sbnd_xarapuca_vuv"), _load("sbnd_xarapuca_vis")
    assert vuv.values["qe"].tolist() == [0.01752, 0.00271] and vis.values["qe"].tolist() == [0.0, 0.01264]
    assert _band_edges(vuv) == _band_edges(vis) == _split_edge()  # the one edge, between the VUV and visible bands
    assert vuv.tts.edges == tuple(float(x) for x in range(21)) and vuv.delay is None
    mean, _ = vis.tts.moments({"pdf": jnp.asarray(vis.values["tts/pdf"])})
    np.testing.assert_allclose(float(mean), 8.5, atol=0.02)  # an exponential of 8.5 ns, uniform within 1 ns bins
    assert vis.delay is not None and len(vis.delay.edges) == 1001
    for m in (vuv, vis):
        g = m.grid((-100.0, 1500.0))
        assert m.readout == "hits" and g.nt > 0 and g.dt <= 1.0
        h = _hist(m, n_sensors=2, gate=(-100.0, 1500.0))
        p = {k: np.asarray(v, np.float32) for k, v in m.defaults("pmt", 2).items()}
        np.testing.assert_allclose(
            np.asarray(rd.pe_density(h, p, dark=False).rate).sum(-1), np.asarray(rd.pe(h, p)), rtol=1e-4
        )


def test_sbnd_recipe_reads_each_sensor_type_and_the_physical_yield(tmp_path):
    """SBND: one modelled group per sbndcode PD type, split by the id map's type column; LAr scintillates as sbndcode's
    LArSoft: standard_properties under opticalproperties_sbnd.fcl at the physical ScintYield, in place of the GDML's
    keys (its yield carries ScintPreScale, its fast share 0.27 is not the muon's)"""
    import dataclasses

    from lumen.gdml import importer

    g = {x.name: x for x in larsoft.SBND.groups}
    assert list(g) == ["pmt_coated", "pmt_uncoated", "xarapuca_vuv", "xarapuca_vis"]
    assert all(x.where == {"type": n} and x.rule == "any_entry" for n, x in g.items())
    want = ["sbnd_pmt", "sbnd_pmt_uncoated", "sbnd_xarapuca_vuv", "sbnd_xarapuca_vis"]
    assert [x.values for x in g.values()] == [f"lumen_tpc:{w}" for w in want]
    df = importer.read_gdml(write(tmp_path, GDML))
    water = df.materials["Water"]
    gdml = {k: schema.Property(key=k, value=np.asarray(v)) for k, v in
            (("SCINTILLATIONYIELD", 720.0), ("SCINTILLATIONYIELD1", 0.27), ("SCINTILLATIONYIELD2", 0.73),
             ("SCINTILLATIONTIMECONSTANT2", 1300.0), ("RESOLUTIONSCALE", 1.0), ("YIELDRATIO", 0.27))}  # fmt: skip
    lar_ = dataclasses.replace(water, name="LAr", properties={**water.properties, **gdml})
    out = larsoft.sbnd_scintillation(dataclasses.replace(df, materials={**df.materials, "LAr": lar_}), {})
    p = out.materials["LAr"].properties
    assert float(p["SCINTILLATIONYIELD"].value) == 24000.0 and "MuonScintYield" in p["SCINTILLATIONYIELD"].note
    assert float(p["SCINTILLATIONYIELD1"].value) == 0.23 and "MuonScintYieldRatio" in p["SCINTILLATIONYIELD1"].note
    t2 = p["SCINTILLATIONTIMECONSTANT2"]
    assert float(t2.value) == 1300.0 and t2.origin == "recipe" and "opticalproperties_sbnd.fcl:26" in t2.note
    assert float(p["SCINTILLATIONTIMECONSTANT1"].value) == 6.0 and float(p["RESOLUTIONSCALE"].value) == 1.0
    assert "RINDEX" in p and "YIELDRATIO" not in p  # the GDML's tables kept, its Geant4 10 keys replaced


def test_microboone_lar_scintillates_as_standard_properties(tmp_path):
    """MicroBooNE: LAr carries LArSoft's tables and standard_properties' scintillation (ScintByParticleType false: the
    fast share ScintYieldRatio), in Geant4 11 keys."""
    import dataclasses

    from lumen.gdml import importer

    df = importer.read_gdml(write(tmp_path, GDML))
    lar_ = dataclasses.replace(df.materials["Water"], name="LAr")
    out = larsoft.microboone_optics(dataclasses.replace(df, materials={**df.materials, "LAr": lar_}), {})
    p = out.materials["LAr"].properties
    assert float(p["SCINTILLATIONYIELD"].value) == 24000.0 and float(p["SCINTILLATIONYIELD1"].value) == 0.3
    assert {"RINDEX", "SCINTILLATIONCOMPONENT1", "SCINTILLATIONCOMPONENT2", "SCINTILLATIONTIMECONSTANT1",
            "SCINTILLATIONTIMECONSTANT2", "SCINTILLATIONYIELD2"} <= set(p)  # fmt: skip
    assert "larproperties.fcl:32 (ScintYieldRatio)" in p["SCINTILLATIONYIELD1"].note


def test_every_shipped_timed_group_has_a_readout_gate():
    """Each recipe's groups whose value set declares a timed readout (hits, waveforms) carry their gate, so simulate
    never refuses one of these detectors for want of one; a ``pe`` readout (an untimed grid) needs none."""
    assert {"sbnd"} <= testing.check_readout_gates(DETECTORS)


def test_sbnd_s_gate_is_read_from_its_scintillation_record():
    """Five of SBND's slow time constants, from the record its scintillation is (no hand-typed number)."""
    from lumen_tpc.larsoft_scintillation import experiment, lar_scintillation

    slow = float(experiment("sbnd")["slow_time_constant"]["value"])
    assert (
        larsoft.SBND_GATE == (0.0, 5 * slow)
        and float(lar_scintillation("sbnd")["SCINTILLATIONTIMECONSTANT2"].value) == slow
    )


def test_the_g4ref_references_gate():
    """g4ref (Geant4 10.7.4; what g4ref changes in it: refs/README.md) on the overlap-free export gates, its run on
    the original GDML named beside it; no entry scales a parameter to pass."""
    gate = testing.check_references_gate(REFERENCES)
    assert gate["sbnd"] and gate["microboone"]
    m = (REFERENCES,)
    for n in ("sbnd", "microboone"):
        assert references.original(references.spec("charge", n, m)["reference"], m) == f"{n}-g4ref-original"


def test_every_detector_s_mc_gate_inputs_are_in_the_manifest():
    """Each detector's MC gate photon file and reference record are files of a manifest product (sha256 pinned): SBND
    and MicroBooNE (the other detectors have no MC gate record)."""
    import json

    m = json.loads(Path(REFERENCES).read_text())
    mc = {e["name"]: e for e in m["checks"]["mc"]}
    assert set(mc) == {"sbnd", "microboone"} and set(mc) <= set(DETECTORS)
    for e in mc.values():
        files = m["products"][e["reference"]]["files"]
        assert e["photons"] in files and e["record"] in files


CPA_GDML = """<?xml version="1.0" encoding="UTF-8"?>
<gdml>
<define/>
<materials>
  <element name="Ar" formula="Ar" Z="18"><atom value="39.95"/></element>
  <material name="LAr"><D value="1.39"/><fraction n="1" ref="Ar"/></material>
  <material name="vm2000"><D value="1.2"/><fraction n="1" ref="Ar"/></material>
  <material name="TPB"><D value="1.4"/><fraction n="1" ref="Ar"/></material>
</materials>
<solids>
  <box name="W" x="4000" y="4000" z="4000" lunit="mm"/>
  <box name="boxCPA_FoilTPB" x="0.050823" y="932" z="1172" lunit="mm"/>
  <box name="boxCPAFoil" x="0.0508" y="932" z="1172" lunit="mm"/>
  <box name="boxCPATPB" x="0.000023" y="932" z="1172" lunit="mm"/>
  <opticalsurface name="Surface_vm2000" model="unified" finish="groundfrontpainted" type="dielectric_dielectric"
    value="0.8"/>
</solids>
<structure>
  <volume name="volCPAFoil"><materialref ref="vm2000"/><solidref ref="boxCPAFoil"/></volume>
  <volume name="volCPATPB"><materialref ref="TPB"/><solidref ref="boxCPATPB"/></volume>
  <volume name="volCPA_FoilTPB"><materialref ref="LAr"/><solidref ref="boxCPA_FoilTPB"/>
    <physvol name="volCPAFoil_PV"><volumeref ref="volCPAFoil"/><position name="pf" x="-0.0000115" unit="mm"/></physvol>
    <physvol name="volCPATPB_PV"><volumeref ref="volCPATPB"/><position name="pt" x="0.0254" unit="mm"/></physvol>
  </volume>
  <skinsurface name="refl_surfaces_vm2000" surfaceproperty="Surface_vm2000"><volumeref ref="volCPAFoil"/></skinsurface>
  <volume name="World"><materialref ref="LAr"/><solidref ref="W"/>
    <physvol name="cpa"><volumeref ref="volCPA_FoilTPB"/><position name="pc" x="1000" unit="mm"/>
      <rotation name="rc" y="180" unit="deg"/></physvol>
  </volume>
</structure>
<setup name="Default" version="1.0"><world ref="World"/></setup>
</gdml>
"""


def test_sbnd_s_cpa_foil_is_split_into_a_tpb_half_and_a_vm2000_half(tmp_path):
    """The 23 nm TPB box is dropped; the foil (50.8 um vm2000) becomes a 25.4 um TPB half on the film's side and a
    25.4 um vm2000 half keeping its skin, flush, inside the foil's old slab, as SBND's GDML places them."""
    from lumen.gdml import importer

    df = larsoft.sbnd_cpa_tpb(importer.read_gdml(write(tmp_path, CPA_GDML)), {})
    assert "volCPATPB" not in df.volumes and "boxCPATPB" not in df.solids
    front, back = df.volumes["volCPAFoilTPB"], df.volumes["volCPAFoil"]
    assert (front.material, back.material) == ("TPB", "vm2000") and front.solid == back.solid
    assert df.solids[front.solid].params["x"] == pytest.approx(25.4e-6, rel=1e-12)
    pos = {p.volume: p.position[0] for p in df.placements if p.mother == "volCPA_FoilTPB"}
    assert pos["volCPAFoilTPB"] == pytest.approx(-11.5e-9 + 12.7e-6, abs=1e-15)  # the film's (+x) side
    assert pos["volCPAFoil"] == pytest.approx(-11.5e-9 - 12.7e-6, abs=1e-15)
    assert [k.surface for k in df.skins if k.volume == "volCPAFoil"] == ["Surface_vm2000"]
    assert any("volCPAFoil" in r and "dropped" in r for r in df.report)


def test_every_input_is_checked_by_one_rule(tmp_path):
    """Every file a conversion reads has a sha256 this package records (SBND's pds_mapping as its GDML); another file,
    or one with another sha256, is refused before anything reads it."""
    import lumen_tpc
    from lumen_tpc import inputs

    d = tmp_path / "gdml"
    d.mkdir()
    for f in ("sbnd_v02_00_full_simulation.gdml", "sbnd_pds_mapping.json"):
        (d / f).write_text("[]")
    gdml, mapping = d / "sbnd_v02_00_full_simulation.gdml", d / "sbnd_pds_mapping.json"
    with pytest.raises(inputs.InputError, match="sbnd_pds_mapping.json has sha256"):
        with lumen_tpc.prepare(larsoft.SBND, gdml, {"pds_mapping": mapping}):
            pass
    with pytest.raises(inputs.InputError, match="records no sha256"):
        lumen_tpc.expected(tmp_path / "other.json")
