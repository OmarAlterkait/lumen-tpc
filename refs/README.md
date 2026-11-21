# How each reference product was made

The products of `src/lumen_tpc/references.json`, each published as a release asset (`<id>.tar.gz`) and fetched on
first use. Each product's `producer` entry in the manifest records the tool, its commit, image and settings.

| Product | Producer |
|---|---|
| `gdml` | `make_store.sh`: the public GDMLs SBND's and MicroBooNE's detector files are converted from (sbndcode, ubcode) and SBND's PDS mapping, copied as published |
| `sbnd-g4ref-original`, `microboone-g4ref-original` | g4ref on the original GDMLs: their producers' `run` blocks with lumen's `tools/g4ref` (`references.sh --runs`, `make_store.sh --runs`) |
| `sbnd-g4ref-export`, `microboone-g4ref-export` | g4ref on the overlap-free exports (`python -m lumen.compare.ownership`), the same way |
| `mc-gate-tpc-3b241f1` | lumen's `tools/g4ref/mc_store.sh STORE ID lumen_tpc ...`: the MC gate's records at lumen 3b241f1 (`python -m lumen.compare gate --package lumen_tpc`, each record's environment inside it and in the producer) and the same photon files; the mc checks gate on it |
| `mc-gate-lartpc-de9e145` | lumen's `tools/g4ref/mc_store.sh STORE ID lumen_tpc ...`: the MC gate's records (`python -m lumen.compare.mc gate --package lumen_tpc`) and its photon files (the id predates the package's name); superseded by mc-gate-tpc-3b241f1 (records before lumen eff19b9, which draws the unpolarised linear state by rng.uniforms: new bits, the same light in expectation) |

`microboone_optics.gdml` (inside `microboone-g4ref-original`) is written by `microboone_optics.py` from the product
`gdml`'s `microboone.gdml` (sha256 f18c8e60...) and this package's LArSoft tables: its output is the stored file byte for
byte (sha256 2268bca0...), and `make_store.sh` refuses a run GDML that differs.

Fixed inputs, kept as stored (no producer in any repository): the source configurations `sbnd_sources_1e7.cfg` and
`microboone_sources_2e7.cfg` (kept inside their g4ref products), the MC gate's photon files (fixed emission rows
sampled once), and `g4ref-events-tpc-933e631d` (two Geant4 events of SBND, a muon of 800 MeV and an electron of 30 MeV,
the notebooks' examples).

`g4ref-gun-sbnd-9fd555c0` (notebook 02's many events: 100 muons of 800 MeV and 100 electrons of 30 MeV at random
places and directions in SBND's TPCs) is made by `events.sh` (lumen's `tools/g4ref/events.py`, on the GDML as
written): its manifest entry gives the binary, the region and the flags, and `events.json` every event's vertex,
direction and seed.

## What g4ref changes in Geant4

g4ref (lumen's `tools/g4ref/g4ref.cc`) links Geant4 10.7.4 unmodified (`G4OpticalPhysics`, photons as primaries). Its
stepping action changes two Geant4 10.7 behaviours, both on by default and used by every g4ref product here:

- the photon's speed after a boundary step (`--no-fix-velocity` turns it off): Geant4 10.7 keeps the speed c a photon
  takes on a zero-length step into a volume without RINDEX (and the old medium's speed after a reflection); g4ref sets
  the GROUPVEL of the medium the photon continues in. `tools/g4ref/velocity_after_relocation.patch` (already in
  `g4ref.cc`) extends it to a reflection after which Geant4 relocated the photon into an overlapping sibling that
  contains the point: the photon continues in that sibling's medium. It moves arrival times, not counts;
- a NoRINDEX kill on a step shorter than 1 um out of a volume without RINDEX into one with RINDEX (`--no-revive`):
  g4ref keeps the photon alive in the medium it re-enters (Geant4 10.7 leaves a photon reflected off a
  dielectric_metal surface inside the volume behind it, and its step back is StepTooSmall only within 1e-9 mm). It
  moves counts.
