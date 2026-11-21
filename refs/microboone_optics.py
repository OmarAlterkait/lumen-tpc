"""Write microboone_optics.gdml, the GDML the g4ref MicroBooNE references read: MicroBooNE's public microboone.gdml
(the product ``gdml``) with LArSoft's public standard optics added, as LArSoft's MaterialPropertyLoader gives them to
Geant4 at run time, from this package's tables (``src/lumen_tpc/data/larsoft_optics_public.json``).

    python refs/microboone_optics.py MICROBOONE_GDML OUT.gdml [TABLES_JSON]

- material LAr: RINDEX, RAYLEIGH (cm), ABSLENGTH (cm) of ``lar.larsoft_standard``. No other material gets RINDEX, so
  Geant4 kills (NoRINDEX) any photon entering one.
- every logical volume of STEEL_STAINLESS_Fe7Cr2Ni: a skin surface of LArSoft's OpBoundaryProcessSimple for that
  material (``surfaces.larsoft_standard``) in its Geant4 form: dielectric_metal, unified, ground, sigma_alpha 0,
  REFLECTIVITY R, SPECULARSPIKECONSTANT 1 - f_diff, SPECULARLOBECONSTANT 0, BACKSCATTERCONSTANT 0 (a share f_diff of
  the reflections is Lambertian), as ``lumen_tpc.larsoft_optics.reflector_tables``.

Nothing else changes: the text is inserted at the end of <define>, <solids> and <structure> and into LAr's <material>.
Every number is written with "%g", which is lossless for these tables (checked here). The input's and the output's
sha256 are printed; the stored microboone-g4ref-original read the output of the shipped tables, sha256
2268bca0b7180cfbcddd15b8f70e7260281e68eff3723d83097583068fdd9065, from microboone.gdml sha256
f18c8e60aefb445b335598727ebd879b9c740cc608a3c85736eae3c4f849e970.
"""

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

STEEL = "STEEL_STAINLESS_Fe7Cr2Ni"
TABLES = Path(__file__).resolve().parents[1] / "src" / "lumen_tpc" / "data" / "larsoft_optics_public.json"


def g(x):
    """Write a number as "%g", refusing one it would round."""
    if float(f"{x:g}") != float(x):
        raise ValueError(f"{x!r} is not exact in %g")
    return f"{x:g}"


def matrix(name, energies, values, unit=""):
    u = f"*{unit}" if unit else ""
    vals = " ".join(f"{g(e)}*eV {g(v)}{u}" for e, v in zip(energies, values, strict=True))
    return f'  <matrix name="{name}" coldim="2" values="{vals}"/>\n'


def enrich(text: str, tables: dict) -> str:
    """Return the GDML text with LArSoft's standard optics added (module docstring)."""
    lar, surf = tables["lar"]["larsoft_standard"], tables["surfaces"]["larsoft_standard"]
    if not (lar["rindex"]["energy_unit"] == "eV" and lar["rayleigh_length"]["value_unit"] == "cm"
            and lar["abs_length"]["value_unit"] == "cm"):  # fmt: skip
        raise ValueError("the tables' units are not eV and cm")
    s, e = surf["surfaces"][STEEL], surf["energies_eV"]
    defs = (matrix("LArRINDEX", lar["rindex"]["energy"], lar["rindex"]["values"])
            + matrix("LArRAYLEIGH", lar["rayleigh_length"]["energy"], lar["rayleigh_length"]["values"], "cm")
            + matrix("LArABSLENGTH", lar["abs_length"]["energy"], lar["abs_length"]["values"], "cm")
            + matrix("SteelREFLECTIVITY", e, s["reflectance"])
            + matrix("SteelSPIKE", e, [1 - f for f in s["diffuse_fraction"]])
            + matrix("SteelLOBE", e, [0.0] * len(e))
            + matrix("SteelBACKSCATTER", e, [0.0] * len(e)))  # fmt: skip
    for tag in ("</define>", "</solids>", "</structure>"):
        if text.count(tag) != 1:
            raise ValueError(f"the GDML has {text.count(tag)} {tag}")
    text = text.replace("</define>", "<!-- g4ref: LArSoft standard optics (lartpc_optics_public.json) -->\n" + defs
                        + "</define>")  # fmt: skip
    m = re.search(r'(<material name="LAr"[^>]*>)(.*?)(</material>)', text, re.S)
    if not m or "<property" in m.group(2):
        raise ValueError("the GDML's LAr is missing or has optical properties already")
    props = ('\n   <property name="RINDEX" ref="LArRINDEX"/>'
             '\n   <property name="RAYLEIGH" ref="LArRAYLEIGH"/>'
             '\n   <property name="ABSLENGTH" ref="LArABSLENGTH"/>\n  ')  # fmt: skip
    steel = [v.get("name") for v in ET.fromstring(text).iter("volume")
             if v.find("materialref") is not None and v.find("materialref").get("ref") == STEEL]  # fmt: skip
    text = text[: m.end(2)] + props + text[m.end(2) :]
    surface = ('  <opticalsurface name="SteelLArSoftSimple" model="unified" finish="ground" type="dielectric_metal" '
               'value="0">\n'
               '   <property name="REFLECTIVITY" ref="SteelREFLECTIVITY"/>\n'
               '   <property name="SPECULARSPIKECONSTANT" ref="SteelSPIKE"/>\n'
               '   <property name="SPECULARLOBECONSTANT" ref="SteelLOBE"/>\n'
               '   <property name="BACKSCATTERCONSTANT" ref="SteelBACKSCATTER"/>\n'
               "  </opticalsurface>\n")  # fmt: skip
    text = text.replace("</solids>", surface + "</solids>")
    skins = "".join(f' <skinsurface name="skinSteel_{i}" surfaceproperty="SteelLArSoftSimple"><volumeref ref="{v}"/>'
                    "</skinsurface>\n" for i, v in enumerate(steel))  # fmt: skip
    return text.replace("</structure>", skins + "</structure>")


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    tables = json.loads(Path(sys.argv[3] if len(sys.argv) > 3 else TABLES).read_text())
    Path(out).write_text(enrich(src.read_text(), tables))
    for p in (src, out):
        print(hashlib.sha256(p.read_bytes()).hexdigest(), p)


if __name__ == "__main__":
    main()
