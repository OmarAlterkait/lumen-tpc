# The LArSoft detectors

lumen-tpc holds the recipes (`lumen_tpc.larsoft`), LArSoft's public optics tables (`lumen_tpc.larsoft_optics`)
and the PMT value sets of SBND and MicroBooNE. Convert one once from its GDML and load its file:

```python
import os
from pathlib import Path

import lumen
from lumen.compare import references

data = references.store()             # the reference data directory: LUMEN_DATA, else lumen's cache (below)
out = Path(os.environ.get("LUMEN_EXAMPLES_OUT", "lumen-examples"))
path = lumen.convert("lumen_tpc:microboone", out=out / "microboone.lumen", data=data, overwrite=True)   # once
det = lumen.load(path)
print(det)
print(len(det.params()), "parameters;", len(det.sensor_table().name), "sensors")
```

| Name | Detector | Sensors | PMT values (sensor model `lumen:sensor`) |
|---|---|---|---|
| `sbnd` | SBND (sbndcode's full-simulation GDML) | PMTs and X-ARAPUCAs, counted on entry, in four groups by sbndcode's type: `pmt_coated` (96), `pmt_uncoated` (24), `xarapuca_vuv` (96), `xarapuca_vis` (96) | `lumen_tpc:sbnd_pmt`, `lumen_tpc:sbnd_pmt_uncoated`, `lumen_tpc:sbnd_xarapuca_vuv`, `lumen_tpc:sbnd_xarapuca_vis` (one per group) |
| `microboone` | MicroBooNE (LArSoft's public optics and scintillation) | the optical-detector discs, counted on entry | `lumen_tpc:microboone_qe` (readout `pe`) |
| `dune_fd1`, `dune_fd1_1x2x6`, `dune_fd2`, `dune_ndlar` | DUNE's far detectors and ND-LAr, their GDML shipped here: [dune.md](dune.md) | X-ARAPUCAs, ArCLight tiles | `lumen_tpc:dune_*` |
| `icarus` | ICARUS, from its inputs given by path (never shipped): [icarus.md](icarus.md) | the PMTs of both cryostats | the PMT input |

SBND has four modelled groups: read each with `light.group("pmt_coated")` and so on. SBND's LAr scintillates as
sbndcode's LArSoft gives it to Geant4: LArSoft's standard_properties under sbndcode's opticalproperties_sbnd.fcl, at the
physical yield, 24000 photons/MeV, with the muon's fast share 0.23 (ScintByParticleType true) and time constants 6 ns
and 1300 ns. These replace the GDML's keys: its yield, 720, carries LArSoft's ScintPreScale, which stands in for the
detection efficiency that the value sets apply here, and its YIELDRATIO 0.27 is not what LArSoft uses. SBND's readout gate is 0 to 6500 ns after emission (five of
LAr's 1.3 µs slow scintillation time constants); `lumen.simulate(..., gate=(start, end))` overrides it for a run.
SBND's GDML gives its scintillation in Geant4 10's keys (FASTCOMPONENT, YIELDRATIO, ...); the recipe replaces them
with the keys above. MicroBooNE's GDML has none: its LAr scintillates as LArSoft's standard_properties (microboone_properties
is standard_properties): 24000 photons/MeV, fast share ScintYieldRatio 0.3, time constants 6 ns and 1590 ns.

## Where the GDML comes from

The GDML files are not in the repository: `lumen_tpc.DETECTORS` names each one's path in the reference data
directory (`references.store()`: `LUMEN_DATA`, else `data` under lumen's cache root):
`gdml/sbnd_v02_00_full_simulation.gdml` with SBND's channel map `gdml/sbnd_pds_mapping.json` (sbndcode), and
`gdml/microboone.gdml` (LArSoft). Both are converted as published. A conversion that finds them missing fetches the
product `gdml` (this repository's release asset) and checks its sha256.

What each recipe decides, and why, is in the module docstring of `lumen_tpc.larsoft`. The value sets are written by
`tools/transcribe.py` from sbndcode v10_26_00, sbnd_data v01_42_00, larsim v10_22_01 (the PhotonHitConverter energy
that splits the VUV and visible bands), uboone's ubevt and ubsim (MicroBooNE's QE), and it writes LArSoft's LAr
tables (`data/larsoft_optics_public.json`) from lardataalg's larproperties.fcl. Every number is parsed from its source and cites its file and line (`provenance.fields`); a number lumen needs that
no source gives (fit ranges, the charge histogram's grid, an efficiency or gain of 1) is a stated choice with its
reason (`provenance.choices`), and the tests check that every field is one or the other. The validation report is
regenerated after a change to the value sets or the recipes.

## Overlapping siblings

SBND's and MicroBooNE's GDML place overlapping siblings (MicroBooNE's wire planes overlap volTPCActive). lumen gives
each shared region one owner (`lumen.geometry.ownership`); Geant4 on the original GDML navigates the overlap its own
way. `lumen.compare.ownership.export(det, path)` writes the overlap-free GDML that says lumen's ownership in Geant4's
terms, so a Geant4 reference runs the geometry lumen simulates. The charge and geometry comparisons gate against
Geant4 on that export (the g4ref products whose producer has an `export`) and report Geant4 on the original GDML beside it; on
MicroBooNE Geant4 on the export sees 0.784 of the light Geant4 on the original sees, on SBND 0.9994 ± 0.0007.

## Validation summary (0.2.0)

From the records in [validation-report.md](validation-report.md) (`python -m lumen.compare charge|gradients`, lumen
3b241f1 with tallymap cba41b6 and jax 0.6.2, RTX 2080 Ti, 2026-11-20). Total charge, lumen over Geant4 10.7.4 (g4ref) on
the overlap-free export, which gates (|z| ≤ 3), with Geant4 on the original GDML reported beside it:

| detector | lumen / Geant4 (export) | lumen / Geant4 (original) | Geant4 export / original |
|---|---|---|---|
| MicroBooNE | 0.9997 ± 0.0009 | 0.7840 ± 0.0007 | 0.7842 ± 0.0008 |
| SBND | 1.0002 ± 0.0006 | 0.9996 ± 0.0006 | 0.9994 ± 0.0007 |

Every gated charge row passes (40 of 40, per-sensor agreement included). MicroBooNE's 0.784 is the overlap effect
(above): its wire planes overlap `volTPCActive`, and Geant4 on the original GDML navigates them its own way, so the
original-GDML rows are reported, never gated. Gradient gates (16 seeds of 32,768 photons; the production comparison on
64 seeds): MicroBooNE 6 of 6, SBND 14 of 14 gated parameter families pass; SBND reports 2 more. SBND's reverse-mode row
(jax.grad of a fixed weighting of the arrivals against fixed-reference finite differences, lumen 96f0633 with tallymap
a7d93d4): largest ratio 0.038, 11 of 11 tested families agree; MicroBooNE has no reverse-mode row.

## Comparisons

`python -m lumen.compare charge|geometry|gradients NAME --package lumen_tpc --detector-file NAME.lumen` runs lumen's
checks (`lumen.compare`) with this package's reference manifest (`src/lumen_tpc/references.json`); the records make
`docs/validation-report.md` (`python -m lumen.compare report`); the reference products are fetched on first use
(`refs/README.md` says how each was made). These, and the gradient gates on 64 seeds, need a GPU and run before a
release, not in CI.
