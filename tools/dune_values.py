"""Write DUNE's sensor value sets (``src/lumen_tpc/sensor_values/dune_*.json``) from published numbers.

    python tools/dune_values.py

Each set holds only numbers with a public source (recorded field by field); a number without one is left out (the
model's default: no TTS, no charge spread) and named in the set's warning. The detection efficiency is the published
photon detection efficiency for LAr scintillation light, per photon entering the counted volume. An X-ARAPUCA's window
is a dichroic filter with its cut-off at 400 nm, which transmits the pTP light (350 nm) and reflects longer
wavelengths (arXiv:2511.20400 sec 2, 2.1): its efficiency is 0 above 400 nm (Cherenkov light the filter reflects) and
the published one below, flat (DUNE's own simulation applies it flat, duneopdet@303d07d2
opticaldetectorservices_dune.fcl:47-50, WavelengthCutLow 0, WavelengthCutHigh 10000 nm, with Cherenkov light off;
between 200 and 400 nm no measurement is published). ArCLight's response off the VUV is not published: flat. The
delay table is the wavelength shifters' re-emission and light-guide decay, convolved; readout ``pe`` (photoelectrons,
with that delay in their times).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "src" / "lumen_tpc" / "sensor_values"

# the delay tables' bin edges, ns: 0.5 ns to 100 ns, 5 ns to 1 us, 50 ns to 8 us, then one bin to 12 us
EDGES = np.concatenate([np.arange(0, 100, 0.5), np.arange(100, 1000, 5.0), np.arange(1000, 8000, 50.0), [8000, 12000]])
FINE, T_MAX = 0.01, 60000.0  # ns: the convolutions' grid and its span

TPB = ((0.60, 2.0), (0.30, 49.0), (0.02, 309.0), (0.08, 3550.0))  # TPB re-emission: (share, ns), Segreto
TAU_EJ280 = 8.5  # ns, EJ-280 WLS plate (ArCLight)
TAU_PTP, TAU_BAR, TAU_BOX = 1.14, 1.2, 2.19  # ns, X-ARAPUCA: pTP, EJ-286 bar, box transport (SBND's)
XA_CUTOFF_NM = 400.0  # the X-ARAPUCA dichroic filter's cut-off: it reflects longer wavelengths (arXiv:2511.20400 sec 2)

SOURCES = {
    "segreto": "TPB re-emission time profile: E. Segreto, Phys. Rev. C 91 (2015) 035503 (60 % 2 ns, 30 % 49 ns, "
    "2 % 309 ns, 8 % 3.55 us)",
    "ej280": "EJ-280 decay 8.5 ns: Eljen datasheet, as used by SBND, arXiv:2406.07514 sec 3.2",
    "sbnd_xa": "X-ARAPUCA pTP 1.14 ns, EJ-286 bar 1.2 ns (arXiv:2406.07514 sec 3.2) and box transport 2.19 ns "
    "(sbndcode's VUV box table, as SBND's reemission projection): SBND's X-ARAPUCA, DERIVED FROM SBND, "
    "not measured for DUNE",
    "daphne": "DAPHNE 62.5 MS/s: DUNE FD2 TDR arXiv:2312.03130, Table PD-Digi-Parameters; the 2x2/ND-LAr light readout "
    "62.5 MHz, arXiv:2509.07012 sec 2.6",
    "dichroic": "0 above 400 nm: the X-ARAPUCA window's dichroic filter has its cut-off at 400 nm, transmits the 350 "
    "nm pTP light and reflects longer wavelengths (arXiv:2511.20400 sec 2 and 2.1); below it the PDE flat, as DUNE's "
    "simulation applies it (duneopdet@303d07d2a0431c7fdab9f485b57b7197d20b4188 "
    "duneopdet/OpticalDetector/opticaldetectorservices_dune.fcl:47-50: QuantumEfficiency 0.03, WavelengthCutLow 0, "
    "WavelengthCutHigh 10000)",
    "dark": "DarkNoiseRate 10 Hz: DUNE/duneopdet@303d07d2a0431c7fdab9f485b57b7197d20b4188 "
    "duneopdet/OpticalDetector/opticaldetectormodules_dune.fcl:24",
}


def _exp(tau):
    return lambda t: np.exp(-t / tau) / tau


def _delay(*densities) -> dict:
    """Return the delay table of the convolved densities, binned on EDGES (the last bin holds the mass past 8 us)."""
    t = np.arange(0.0, T_MAX, FINE)
    n = 2 * len(t)
    f = None
    for d in densities:
        g = d(t) * FINE
        f = g if f is None else np.fft.irfft(np.fft.rfft(f, n) * np.fft.rfft(g, n), n)[: len(t)]
    cdf = np.interp(EDGES, np.concatenate([t, [T_MAX]]), np.concatenate([[0.0], np.cumsum(f)]))
    pdf = np.diff(cdf)
    pdf[-1] += max(0.0, 1.0 - cdf[-1])
    pdf = pdf / pdf.sum()
    return {"form": "table", "edges_ns": [float(x) for x in EDGES], "pdf": [float(x) for x in pdf]}


def _set(name, pde, pde_source, delay, delay_source, dark, warning, cutoff_nm=None) -> dict:
    return {
        "schema": "lumen-sensor-values/1", "model": "lumen:sensor", "name": name, "readout": "pe",
        "provenance": {"source": pde_source, "status": "unverified",
                       "fields": {"qe": pde_source, "delay": delay_source, "frontend": SOURCES["daphne"],
                                  "dark_rate": SOURCES["dark"] if dark else "not published: 0"},
                       "warning": warning},
        "qe": ({"band_edges_nm": [], "values": [pde]} if cutoff_nm is None else
               {"band_edges_nm": [cutoff_nm], "values": [pde, 0.0]}), "ce": None, "efficiency": 1.0, "t_offset_ns": 0.0,
        "tts": None, "delay": delay, "charge": None, "gain": 1.0, "threshold": None, "dark_rate_hz": dark,
        "ranges": {"t_offset": [-10.0, 10.0]},
        "frontend": {"sampling_ns": 16.0, "unit": "pe", "window_ns": 0.0, "charge_step_pe": 0.25, "charge_max_pe": 4.0},
    }  # fmt: skip


COMMON_GAPS = "not published, left out: the single-photoelectron time spread and charge spread"
XA_GAPS = ("not published: the PDE's wavelength dependence below the filter's 400 nm cut-off (flat there: Cherenkov "
           "light of 200-400 nm is counted at it); " + COMMON_GAPS + "; the SiPM cross-talk")  # fmt: skip
ARC_GAPS = ("not published: the PDE's wavelength dependence (flat: Cherenkov light outside the VUV is counted at "
            "it); " + COMMON_GAPS)  # fmt: skip


def sets() -> dict:
    """Return the value sets by name."""
    xa = _delay(_exp(TAU_PTP), _exp(TAU_BAR), _exp(TAU_BOX))
    xa_src = SOURCES["sbnd_xa"]
    return {
        "dune_fd1_xarapuca": _set(
            "dune_fd1_xarapuca", 0.025,
            "PDE 2.5 %: the FD1 (horizontal drift) X-ARAPUCA baseline, arXiv:2511.20400 Table 1 (2.5-4.6 % with the "
            "optimised assembly); LArSoft's DUNE simulation uses 3 % (duneopdet@303d07d2 "
            "opticaldetectorservices_dune.fcl:47); " + SOURCES["dichroic"], xa, xa_src, 10.0, XA_GAPS, XA_CUTOFF_NM),
        "dune_fd2_xarapuca": _set(
            "dune_fd2_xarapuca", 0.037,
            "PDE 3.7 %: the lower end of the FD2 (vertical drift) X-ARAPUCA range 3.7-4.5 %, arXiv:2511.20400 Table 1 "
            "and arXiv:2312.03130 sec 1.3.4; single- and double-sided modules alike; " + SOURCES["dichroic"], xa,
            xa_src, 10.0, XA_GAPS, XA_CUTOFF_NM),
        "dune_ndlar_arclight": _set(
            "dune_ndlar_arclight", 0.0019,
            "PDE 0.19 % (+- 0.02 %): the 2x2 demonstrator's ArCLight, L. Calivers, PhD thesis, University of Bern "
            "(2025), boristheses.unibe.ch/6310 (the abstract's number; per photon on the tile face)",
            _delay(lambda t: sum(a * _exp(tau)(t) for a, tau in TPB), _exp(TAU_EJ280)),
            f"{SOURCES['segreto']}, convolved with {SOURCES['ej280']}; the plate's transport time is not published "
            "(left out)", 0.0, ARC_GAPS + "; the dark rate; the plate's transport time"),
    }  # fmt: skip


def main() -> None:
    """Write the sets."""
    for name, d in sets().items():
        (OUT / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
        print(name, "written")


if __name__ == "__main__":
    main()
