"""lumen for liquid-argon TPC detectors (LArSoft: SBND, MicroBooNE, ICARUS; DUNE).

    import lumen
    from lumen.compare import references
    path = lumen.convert("lumen_tpc:sbnd", out="sbnd.lumen", data=references.store())   # recipe, GDML, inputs, once
    det = lumen.load(path)

The recipes are ``lumen_tpc.larsoft`` (LArSoft's public optics tables: ``lumen_tpc.larsoft_optics``); the PMT
value sets are ``lumen_tpc:<set>`` (``sensor_values/<set>.json``); the reference manifest of the comparisons is
``REFERENCES`` (``python -m lumen.compare ... --package lumen_tpc``). SBND's and MicroBooNE's GDML have overlapping
siblings: lumen's ``lumen.compare.ownership.export`` writes their overlap-free GDML.
"""

from __future__ import annotations

from pathlib import Path

from lumen import DetectorEntry
from lumen.inputs import package
from lumen_tpc import dune, icarus, larsoft
from lumen_tpc.inputs import GDML_DIR

REFERENCES = Path(__file__).parent / "references.json"
# name: lumen.DetectorEntry (the recipe, its GDML under the data directory, the recipe's inputs there); both GDMLs as
# published, fetched with the product gdml when the directory lacks them
DETECTORS: dict[str, DetectorEntry] = {
    "sbnd": DetectorEntry(
        recipe=larsoft.SBND,
        gdml="gdml/sbnd_v02_00_full_simulation.gdml",
        inputs={"pds_mapping": "gdml/sbnd_pds_mapping.json"},
    ),
    "microboone": DetectorEntry(recipe=larsoft.MICROBOONE, gdml="gdml/microboone.gdml"),
    # DUNE: the GDMLs ship here (xz, gdml/SOURCES.json); ``data`` is not read
    "dune_fd1": DetectorEntry(recipe=dune.FD1, gdml=GDML_DIR / "dune10kt_v6_refactored_nowires.gdml.xz"),
    "dune_fd1_1x2x6": DetectorEntry(recipe=dune.FD1_1X2X6, gdml=GDML_DIR / "dune10kt_v6_refactored_1x2x6.gdml.xz"),
    "dune_fd2": DetectorEntry(recipe=dune.FD2, gdml=GDML_DIR / "dunevd10kt_3view_30deg_v6_refactored_nowires.gdml.xz"),
    "dune_ndlar": DetectorEntry(
        recipe=dune.NDLAR, gdml=GDML_DIR / "nd_hall_with_lar_tms_sand_TDR_Production_geometry_v_1.0.3.gdml.xz"
    ),
    # ICARUS: ``data`` is the directory of its inputs, never shipped (icarus.INPUTS: their sha256 and provenance); its
    # recipe is made from them, after checking them
    "icarus": DetectorEntry(
        recipe=icarus.ICARUS,
        gdml=icarus.INPUTS["gdml"]["file"],
        inputs={k: icarus.INPUTS[k]["file"] for k in ("optics", "pmt")},
    ),
}


# the package's prepare (lumen.convert("lumen_tpc:NAME")) and the sha256 of each file a conversion reads: lumen's one
# input pipeline (lumen.inputs.package), with ICARUS's inputs given by path recorded by file name (icarus.INPUTS); a
# recipe made from its inputs (icarus.InputRecipe) is made after the check
prepare, expected = package(
    REFERENCES, GDML_DIR, {v["file"]: (v["sha256"], v["source"]) for v in icarus.INPUTS.values()}
)
