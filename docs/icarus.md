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

## Using ICARUS, step by step

This is for someone with access to ICARUS's inputs who wants to simulate, differentiate or calibrate ICARUS's light
with lumen. Everything else in lumen-tpc works for ICARUS as it does for SBND: the notebooks (`notebooks/`, SBND as
the running example) are the tutorial, and each step below says what differs. Nothing of ICARUS goes back into this
repository: keep the inputs, the converted detector and your results outside it.

### 1. The three inputs

Put the three files in one directory, under the names `lumen_tpc.icarus.INPUTS` gives:

| Input | File | What it is |
|---|---|---|
| `gdml` | `INPUTS["gdml"]["file"]` | ICARUS's GDML, from SBNSoftware's icarusalg geometry, as published (not repaired) |
| `optics` | `INPUTS["optics"]["file"]` | the transcription of ICARUS's optical fcl (the JSON form below) |
| `pmt` | `INPUTS["pmt"]["file"]` | the PMT value set (`lumen-sensor-values/1`, lumen's [value sets](https://github.com/OmarAlterkait/lumen/blob/v0.2.0/docs/reference/value-sets.md)) |

`INPUTS[name]["source"]` says where each file comes from. Check them before converting; the recipe checks them too:

```python
import hashlib
from pathlib import Path
from lumen_tpc import icarus

icarus_inputs_dir = Path("/path/to/icarus-inputs")
for name, i in icarus.INPUTS.items():
    p = icarus_inputs_dir / i["file"]
    ok = p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == i["sha256"]
    print(f"{name:7s} {i['file']}: {'ok' if ok else 'MISSING or a different file'}")
```

The optics input is one JSON object, which the recipe and `lumen_tpc.runs` read:

- `lar`: ICARUS's overrides of lardataalg's standard_properties, `{"overrides": {entry: {"value": ..., "source":
  ...}}}`, the record form of every LArSoft experiment (`src/lumen_tpc/data/larsoft_optics_public.json`, `lar.sbnd`,
  is one; `lumen_tpc.larsoft_scintillation` reads it);
- `surfaces`: `energies_eV` (the photon energies of the tables), `reflectivity` (`{material: [REFLECTIVITY at each
  energy]}`: every volume of that material gets a reflector skin), and the surface's `type`, `model`, `finish` and
  `polish`, as Geant4 names them;
- `provenance`: `reflective_surfaces` and `surface`, the sources the detector file records for those tables and for
  the surface;
- `runs`: `{run name: {"lights": [...], "scale": {key: factor}, "values": {key: value}, "source": "..."}}`, the
  reference runs (`lumen_tpc.runs.Run.of`); `larsoft` is ICARUS's LArSoft run.

### 2. Convert once

```python
import lumen

path = lumen.convert("lumen_tpc:icarus", out="/path/to/work/icarus.lumen", data=icarus_inputs_dir)
det = lumen.load(path)
print(det)
for line in det.file.report:   # every decision, and the placement check's verdict
    print("-", line)
```

As for SBND (notebook 01), the conversion applies lumen's import rules and the recipe's decisions, checks the
structure and runs the placement check; where the GDML's volumes overlap, the report names the owner lumen gives each
shared region. ICARUS is large (two cryostats), so its conversion and its first compile take longer than SBND's. The
sensors, in the order every result uses, are `det.sensor_table()`.

### 3. Simulate light

Any of lumen's [sources](https://github.com/OmarAlterkait/lumen/blob/v0.2.0/docs/howto/sources.md) runs on ICARUS. Use
positions in m in the GDML's frame, inside the argon:

```python
src = lumen.sources.Point(position=(x, y, z), lam=128.0, n_photons=1e6)   # argon's scintillation light
light = lumen.simulate(det, src, samples=2**18, seed=0)
pe = lumen.readout.pe(light, det.params())                             # expected photoelectrons per PMT
```

For a particle, give its charged steps (from your own Geant4 or LArSoft run) as `ScintillationSteps.of(det.params(),
"LAr", start=, end=, t_start=, t_end=, edep=)` and `CherenkovSteps("LAr", ...)`, or as an event file that
`lumen.compare.event.read` reads, then `event.simulate(det, ev, samples=2**18, seed=0)` (notebook 00).
`lumen.tools.plot.event(det, pe, light.mean_arrival_time)` draws the event display.

### 4. Physical, or as ICARUS's LArSoft ran

The detector file is physical: LAr's full scintillation yield and Cherenkov light. To compare with ICARUS's own
LArSoft/Geant4 output, run with its settings (the run modes above) and emit only `run.lights`:

```python
run = runs.config("icarus", "larsoft", inputs={"optics": icarus_inputs_dir / icarus.INPUTS["optics"]["file"]})
res = event.compare(det, ev, run.params(det.params()), lights=run.lights, samples=2**18, seed=0)
```

`event.compare` needs the event's Geant4 hits as well as its steps (notebook 02). This package ships no ICARUS
reference run, so there is no ICARUS charge check (`lumen.compare.charge`) or MC gate here: a comparison with
ICARUS's output is yours to make and keep.

### 5. Derivatives and calibration

Every optical number of the detector file is a parameter (`det.params()`; `p.explain(key)` says where its value came
from). Notebooks 03 and 04 show derivatives of a run by each parameter, checked against finite differences, and a
calibration of LAr's optics by gradient steps and by Fisher scoring. On ICARUS, load `icarus.lumen` in their place of
`sbnd.lumen` and take the keys from ICARUS's detector: `materials/LAr/ABSLENGTH` and `materials/LAr/RAYLEIGH` are
the same, but SBND's reflector `surfaces/Surface_vm2000/REFLECTIVITY` is ICARUS's `surfaces/reflector:<material>/
REFLECTIVITY`, one per material of the optics input (`[k for k in det.params() if k.startswith("surfaces/")]`) and
their events are SBND's, so give your own sources. The family's gradient check (`python -m lumen.compare
gradients`) runs the entries of this package's reference manifest, which has no ICARUS entry.

### 6. Another version of the inputs

The recipe accepts only the files whose sha256 `INPUTS` holds; a newer GDML or optics fcl is refused, by name, rather
than read silently. To use another version, write its three files and change `INPUTS` (file, sha256 and source) in
your installed copy, or propose the change to this repository: it then still holds only those three records, never
the files. If the new GDML renames the sensors' volume or the detector volume, `SENSOR_LV` and `DETECTOR_VOLUME` in
`lumen_tpc.icarus` change with it.
