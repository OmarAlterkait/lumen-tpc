# DUNE

lumen-tpc converts DUNE's far detectors and ND-LAr from DUNE's public GDML, which ships here (xz-compressed,
`src/lumen_tpc/gdml/`, each file's URL, commit and sha256 in `gdml/SOURCES.json`; the sha256 is checked when it is
converted). No data directory is read:

```python
import lumen
det = lumen.load(lumen.convert("lumen_tpc:dune_fd2", out="dune_fd2.lumen", data="."))
```

| Name | Detector (GDML) | Sensors, counted on entry | Value set (`lumen:sensor`, readout `pe`) |
|---|---|---|---|
| `dune_fd1` | FD1, horizontal drift, no wires (dunecore `dune10kt_v6_refactored_nowires`) | 6000 X-ARAPUCA windows | `lumen_tpc:dune_fd1_xarapuca` |
| `dune_fd1_1x2x6` | FD1's 1x2x6 workspace with its wires (`dune10kt_v6_refactored_1x2x6`), a smaller test geometry | 480 | `lumen_tpc:dune_fd1_xarapuca` |
| `dune_fd2` | FD2, vertical drift, no strips (`dunevd10kt_3view_30deg_v6_refactored_nowires`) | 672 X-ARAPUCAs (352 membrane, 320 double-sided cathode) | `lumen_tpc:dune_fd2_xarapuca` |
| `dune_ndlar` | ND-LAr in the ND hall (2x2_sim `nd_hall_with_lar_tms_sand_TDR_Production_geometry_v_1.0.3`), its 35 modules under their common mother `volArgonCubeDetector75` | 1400 ArCLight tiles (their LAr-side TPB layer `volTPB_LAr`) | `lumen_tpc:dune_ndlar_arclight` |

For physics use the full FD2, not its 1x8x6 workspace (not shipped), which under-reads the cathode light. What the
recipes decide is in the module docstring of `lumen_tpc.dune`: LArSoft's LAr tables and steel reflector (DUNE's
`SimpleBoundaryProcess` is true), LAr's LArSoft scintillation at its physical yield, every other material opaque.

## The two run modes

- **physical** (the default, how the detector is converted and run): Cherenkov light on, LAr's full physical
  scintillation yield (24000 photons/MeV), no prescale. The value sets apply the detection efficiency.
- **larsoft** (a comparison with DUNE's own LArSoft/Geant4 output only): DUNE's fcl runs with `ScintPreScale` 0.05
  and `EnableCerenkovLight` false (dunecore `larproperties_dune.fcl`). These are run settings, not detector physics:

```python
from lumen_tpc import runs
run = runs.config("dune_fd2", "larsoft")
params = run.params(det.params())          # SCINTILLATIONYIELD x 0.05, for this run only
# emit only the lights in run.lights (here scintillation); the detector file is unchanged
```

ND-LAr is not simulated with LArSoft: it has no reference run.

There is no readout gate: DUNE publishes no light readout window after emission (duneopdet's digitizer reads triggered
waveform windows of 1000 ticks, duneopdet 303d07d2 opticaldetectormodules_dune.fcl:28-36). A timed run passes its own,
`lumen.simulate(..., gate=(start, end))`.

## The value sets

`tools/dune_values.py` writes them from published numbers (status `unverified`; sources field by field): the photon
detection efficiency for LAr scintillation light (FD1 X-ARAPUCA 2.5 %, arXiv:2511.20400; FD2 3.7 %, the low end of
3.7-4.5 %, arXiv:2511.20400 and the FD2 TDR; ArCLight 0.19 %, the 2x2 demonstrator, Calivers' thesis), and the full
wavelength-shifter delay table (ArCLight: TPB re-emission, Segreto, convolved with EJ-280; X-ARAPUCA: pTP, bar and box
times derived from SBND's, not measured for DUNE). An X-ARAPUCA's efficiency is 0 above 400 nm: its window's dichroic
filter has its cut-off there and reflects longer wavelengths (arXiv:2511.20400 sec 2), so the physical run's Cherenkov
light above 400 nm is not counted; below it the efficiency is flat, as DUNE's own simulation applies it (duneopdet
opticaldetectorservices_dune.fcl, no wavelength cut, Cherenkov light off). Left out, with no public number: the
efficiency's wavelength dependence below 400 nm (X-ARAPUCA) and at every wavelength (ArCLight: flat, so its visible
Cherenkov light is counted at the scintillation efficiency), the single-photoelectron time and charge spread, the SiPM
cross-talk, ND-LAr's dark rate and plate transport time.

## Open

- ND-LAr's real light system mixes ArCLight and LCM (the CDR: 20 ArCLight + 60 LCM per module); the TDR GDML has the
  ArCLight geometry only and the slot map is not public, so ND-LAr is converted as the GDML gives it.
- The delay tables span 12 µs in 0.5 ns bins near zero: a timed grid with them can run out of memory (readout work).
- FD1 with every wire (`dune10kt_v6_refactored`) converts but takes tens of minutes to load: not registered.
- Xe doping (FD2 option) is not modelled; duneopdet's Xe constants are in µs·ppm (10 ppm: a 393 ns triplet).
- LArSoft's fast share is per particle (ScintByParticleType); a material holds one, the muon's (0.23).
