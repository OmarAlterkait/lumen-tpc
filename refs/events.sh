#!/bin/bash
# Make g4ref-gun-sbnd-<g4ref>: Geant4 events of SBND for notebook 02's many-event comparison
# (lumen.compare.event.compare_events), with lumen's tools/g4ref/events.py.
#
#   events.sh OUT                 the table (once), then the runs: a Slurm array task K of N runs its rows
#   sbatch --array 0-49 events.sh OUT
#
# 100 mu- of 800 MeV and 100 e- of 30 MeV, vertices uniform in the TPCs' active volume (x within 1.9 m of the
# cathode, |y| < 1.8 m, 0.3 m < z < 4.7 m), isotropic directions; one Geant4 run per event on SBND's GDML as written
# (its LAr scintillation: compared with lumen's run named gdml, lumen_tpc.runs), Cherenkov and scintillation on,
# --split-ev 6.19. Each event file records its vertex, direction, seed and flags.
set -euo pipefail
OUT=$1
EVENTS=${G4REF_TOOLS:?the tools/g4ref directory of lumen}/events.py
G4REF=${G4REF:?the g4ref binary (tools/g4ref/build.sh)}
GDML=${LUMEN_DATA:?the reference store}/gdml/sbnd_v02_00_full_simulation.gdml
PY=${LUMEN_PY:-python3}
if [ ! -f "$OUT/events.json" ]; then
  $PY "$EVENTS" table "$OUT" --name sbnd --particle mu- --mev 800 --n 100 --seed 21 --region box:-1.9,1.9,-1.8,1.8,0.3,4.7
  $PY "$EVENTS" table "$OUT" --name sbnd --particle e- --mev 30 --n 100 --seed 22 --region box:-1.9,1.9,-1.8,1.8,0.3,4.7
fi
$PY "$EVENTS" run "$OUT" --g4ref "$G4REF" --gdml "$GDML" --sens-regex '^volOpDetSensitive' \
  --task "${SLURM_ARRAY_TASK_ID:-0}" --tasks "${SLURM_ARRAY_TASK_COUNT:-1}" --cherenkov --scintillation --split-ev 6.19
