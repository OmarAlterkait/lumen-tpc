# ICARUS

ICARUS's inputs are not in this repository. lumen-tpc converts ICARUS when they are given, by path, at conversion:
a directory holding the three files `lumen_tpc.icarus.INPUTS` names (the GDML, the optics transcription and the PMT
value set), each with the sha256 the recipe expects and where it comes from. Without them, or with another file, the
recipe refuses and names what is missing:

```python
import lumen
det = lumen.load(lumen.convert("lumen_tpc:icarus", out="icarus.lumen", data=icarus_inputs_dir))
```

The recipe (`lumen_tpc.icarus`) is LArSoft's legacy optical loader read from those inputs: LAr with LArSoft's tables
and its scintillation at the physical yield (the optics input's `lar` record, ICARUS's fcl overrides of
standard_properties in the form `lumen_tpc.larsoft_scintillation` reads for every LArSoft experiment), a reflector
skin on every volume of each material the optics input lists, every other material opaque, the `volOpDetSensitive`
shells counted on entry and read by `lumen:sensor` with the PMT input. The detector volume is `volDetEnclosure`, the
common mother of both cryostats (360 PMTs).

## The two run modes

- **physical** (the default, how the detector is converted and run): Cherenkov light on, LAr's full physical
  scintillation yield, no prescale.
- **larsoft** (a comparison with ICARUS's own LArSoft/Geant4 output only): the settings of ICARUS's LArSoft run, held
  in the optics input's `runs` record (with their sources), applied to the run, never to the detector file:

```python
from lumen_tpc import icarus, runs
run = runs.config("icarus", "larsoft", inputs={"optics": icarus_inputs_dir / icarus.INPUTS["optics"]["file"]})
params = run.params(det.params())          # the run's values; emit only the lights in run.lights
```
