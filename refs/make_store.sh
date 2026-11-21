#!/bin/bash
# Build the reference store: every product lumen-tpc's checks read, reduced by tools/g4ref/reduce.py, read-only.
#
#   make_store.sh STORE G4REF_RUNS
#
# The g4ref products are the runs of the reference manifest's g4ref products (src/lumen_tpc/references.json: their
# producers' run blocks; lumen tools/g4ref/references.sh --runs) in G4REF_RUNS, reduced by
# lumen's tools/g4ref/make_store.sh --runs (microboone_optics.gdml: written by refs/microboone_optics.py, checked
# here); the product "gdml" copies the GDMLs the detector files are converted from.
# Prints each product's manifest entry.
set -euo pipefail
STORE=$1; RUNS=$2
HERE=${G4REF_TOOLS:?the tools/g4ref directory of lumen (reduce.py, make_store.sh)}
D=${LUMEN_SITE_DATA:?the directory holding geom_query/gdml and lumen/g4ref}
export IMAGE=${IMAGE:?the container image the g4ref runs used} G4REF_SRC=${G4REF_SRC:?the g4ref source file the runs were built from}

# microboone_optics.gdml, which the microboone run reads, is refs/microboone_optics.py's output on the product gdml's
# microboone.gdml: refuse a run GDML that is not what the producer writes
PY=${LUMEN_PY:-python3}
TMP=$(mktemp -d -p "${STORE_TMP:-/tmp}"); trap 'rm -rf "$TMP"' EXIT
$PY "$(dirname "$0")/microboone_optics.py" "$D/geom_query/gdml/microboone.gdml" "$TMP/microboone_optics.gdml"
cmp "$TMP/microboone_optics.gdml" "$D/lumen/g4ref/geom/microboone_optics.gdml" ||
  { echo "lumen/g4ref/geom/microboone_optics.gdml is not refs/microboone_optics.py's output"; exit 1; }
# the g4ref products: lumen's tools/g4ref/make_store.sh over this package's manifest
bash "$HERE/make_store.sh" "$STORE" "$RUNS" --runs "$(cd "$(dirname "$0")/.." && pwd)/src/lumen_tpc/references.json"
# the GDMLs the public detector files were converted from
[ -e "$STORE/gdml/MANIFEST.json" ] || mkdir -p "$STORE/gdml"
[ -e "$STORE/gdml/MANIFEST.json" ] || for f in $D/geom_query/gdml/sbnd_v02_00_full_simulation.gdml \
         $D/geom_query/gdml/sbnd_pds_mapping.json $D/geom_query/gdml/microboone.gdml; do
  [ -e "$STORE/gdml/$(basename "$f")" ] || { cp "$f" "$STORE/gdml/"; chmod 0444 "$STORE/gdml/$(basename "$f")"; }
done
(cd "$STORE/gdml" && sha256sum ./*)
