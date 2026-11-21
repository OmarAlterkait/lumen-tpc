"""Write lumen-tpc's value sets and LArSoft optics tables from sbndcode, sbnd_data, larsim, LArSoft and uboone.

    python tools/transcribe.py --out src/lumen_tpc/sensor_values
        --optics src/lumen_tpc/data/larsoft_optics_public.json
        --sbndcode SBNDCODE --sbnd-data SBND_DATA --larsim LARSIM --lardataalg LARPROPERTIES_FCL
        --ubevt PMTCONFIG_MICROBOONE_FCL --ubsim UBOPTICALCHCONFIG_CC
        --fcl dune=LARPROPERTIES_DUNE_FCL
        --fcl microboone=LARPROPERTIES_MICROBOONE_FCL
    python tools/transcribe.py --optics src/lumen_tpc/data/larsoft_optics_public.json --lardataalg LARPROPERTIES_FCL
        --fcl sbnd=OPTICALPROPERTIES_SBND_FCL --fcl dune=... --fcl microboone=...   (the tables only)

SBNDCODE: the sbndcode v10_26_00 product (its fcl/ and source/sbndcode/OpDetSim/; SBNDSoftware/sbndcode tag v10_26_00 =
commit b21d990d). SBND_DATA: the sbnd_data v01_42_00 product (OpDetSim/*.root, CalibrationDatabase/pds_calibration.db).
LARSIM: the larsim v10_22_01 product sbndcode v10_26_00 runs with (through sbncode and larsoft v10_26_00; its
source/larsim/PhotonHitConverter/). LARPROPERTIES_FCL: LArSoft/lardataalg 03f5e9a2
lardataalg/DetectorInfo/larproperties.fcl. PMTCONFIG_MICROBOONE_FCL: uboone/ubevt 14ad3eb1
ubevt/Utilities/pmtconfig_microboone.fcl. UBOPTICALCHCONFIG_CC: uboone/ubsim df3e2431
ubsim/OpticalDetectorSim/UBOpticalChConfig.cc. The ROOT vectors are read with uproot, the calibration with sqlite3.
``--fcl NAME=FILE``: each LArSoft experiment's fcl over standard_properties (``EXPERIMENTS``: its file at its commit);
SBND's is sbndcode's opticalproperties_sbnd.fcl, from SBNDCODE unless given.

Every number is parsed from its source and records its file:line in ``provenance.fields``; a number a set needs that
no source gives is a choice of this package, stated with its reason in ``provenance.choices``. Nothing is typed in.
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

import numpy as np

from lumen.units import wavelength_of

SBNDCODE = "SBNSoftware/sbndcode v10_26_00 (commit b21d990d4e60e30118d462f1bd303a94bfdf0a37)"
SBND_DATA = "SBNSoftware/sbnd_data v01_42_00 (commit 8f3deb61ebe4ea61fa09e8b5721394be64ed1c63)"
LARSIM = "LArSoft/larsim v10_22_01 (commit 72d698f8dece3570bd70b20ddfc63eb5544aaae6)"
LARDATAALG = "LArSoft/lardataalg 03f5e9a2e1cec38be040f91fdd662c9d54ee0667"
UBEVT = "uboone/ubevt 14ad3eb1397a6ced617eba36dc5d035a64bd196e"
UBSIM = "uboone/ubsim df3e2431947564443289d1a9e2cc1bedb0fec642"
DUNECORE = "DUNE/dunecore 1861034bf807a2f556a476615c0a0f212dc43a0e"
# each LArSoft experiment whose numbers this repository may hold: its fcl over standard_properties (the file that sets
# its LArProperties' scintillation, at its commit) and the fcl table that is its LArProperties; the first line of each
# key in that table is read. A detector whose inputs are given by path carries its record in its own input
EXPERIMENTS = {
    "dune": (f"{DUNECORE} dunecore/Utilities/larproperties_dune.fcl", "dunefd_properties"),
    "microboone": (f"{UBEVT} ubevt/Utilities/larproperties_microboone.fcl", "microboone_properties"),
    "sbnd": (f"{SBNDCODE} sbndcode/LArSoftConfigurations/opticalproperties_sbnd.fcl", "sbnd_opticalproperties"),
}


def github(ref):
    """The URL of a "<owner/repo> <commit>" or "<owner/repo> <tag> (commit <hash>)" reference at its commit."""
    repo, *rest = ref.split()
    return f"https://github.com/{repo}/tree/{rest[-1].rstrip(')')}"


SBND_REF = (
    f"{SBNDCODE} ({github(SBNDCODE)}): sbndcode/OpDetSim/{{digi_pmt_sbnd.fcl, digi_arapuca_sbnd.fcl, "
    "DigiPMTSBNDAlg.cc, DigiPMTSBNDAlg.hh, DigiArapucaSBNDAlg.cc, opDetDigitizerWorker.cc}, "
    "sbndcode/LArSoftConfigurations/{detectorclocks_sbnd.fcl, opticalproperties_sbnd.fcl}, "
    f"calibration_database_PDS_TagSets_sbnd.fcl; {SBND_DATA} ({github(SBND_DATA)}): "
    "OpDetSim/digi_pmt_sbnd_v2int0.root, OpDetSim/digi_arapuca_sbnd.root, CalibrationDatabase/pds_calibration.db; "
    f"{LARSIM} ({github(LARSIM)}): larsim/PhotonHitConverter/PhotonHitConverter_module.cc"
)

RANGES_CHOICE = (
    "the bounds of each timing value a fit may reach: lumen:sensor builds its static time grid for them (a value "
    "outside is refused); not experiment data. A time spread's width has none here: its range is lumen's derived one "
    "(lumen.rules.choices.TIME_SPREAD_REACH)"
)
CHOICES = {
    "efficiency": "1: no per-sensor scale beyond the detection efficiency in qe",
    "frontend/charge_scale": "1: the charge in units of the single photoelectron",
    "frontend/charge_noise_pe": "0: no charge noise beyond the single photoelectron's spread (charge)",
    "frontend/window_ns": "0: no integration window (each photoelectron its own pulse or hit)",
    "frontend/charge_step_pe": "0.25: the charge histogram's step, a quarter of a photoelectron",
}


class Text:
    """A source file's lines, searched by pattern."""

    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name
        self.lines = self.path.read_text().splitlines()

    def find(self, pattern):
        """[(line, match)] of every line matching ``pattern``, 1-based."""
        return [(i, m) for i, ln in enumerate(self.lines, 1) if (m := re.search(pattern, ln))]

    def one(self, pattern):
        """(match, line) of the one line matching ``pattern``."""
        hits = self.find(pattern)
        if len(hits) != 1:
            raise ValueError(f"{self.name}: {len(hits)} lines match {pattern!r} (want 1)")
        return hits[0][1], hits[0][0]

    def lines_of(self, pattern):
        """ "<l1>, <l2>, ...": the lines matching ``pattern`` (at least one)."""
        hits = self.find(pattern)
        if not hits:
            raise ValueError(f"{self.name}: no line matches {pattern!r}")
        return ", ".join(str(i) for i, _ in hits)

    def at(self, pattern):
        """ "<name>:<l1>, <l2>, ...": the lines matching ``pattern``."""
        return f"{self.name}:{self.lines_of(pattern)}"


def fcl_values(path, keys):
    """{key: (value, line)} of the first `key: value` line of each key in an fcl file."""
    out = {}
    for i, ln in enumerate(Path(path).read_text().splitlines(), 1):
        m = re.match(r"\s*(?:\w+\.)*(\w+):\s*([-+0-9.eE]+)", ln.split("#")[0])
        if m and m.group(1) in keys and m.group(1) not in out:
            out[m.group(1)] = (float(m.group(2)), i)
    if set(keys) - set(out):
        raise ValueError(f"{path}: no line gives {sorted(set(keys) - set(out))}")
    return out


def fcl_array(path, key):
    """(tokens, first line, last line) of an fcl array `key: [ ... ]`, comments removed; an array of arrays gives a
    list of token lists."""
    lines = Path(path).read_text().splitlines()
    i0 = next(i for i, ln in enumerate(lines) if re.match(rf"\s*{key}\s*:\s*\[", ln.split("#")[0]))
    text, i = "", i0
    while True:
        text += lines[i].split("#")[0] + "\n"
        if text.count("[") == text.count("]"):
            break
        i += 1
    body = text.split(":", 1)[1].strip()[1:-1]
    rows = re.findall(r"\[([^\[\]]*)\]", body)

    def split(s):
        return [t for t in re.split(r"[,\s]+", s) if t]

    return ([split(r) for r in rows] if rows else split(body)), i0 + 1, i + 1


def number(token):
    """A source token as JSON writes it: its own integer or decimal form ("8000." -> 8000.0)."""
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        return float(token)


def base(name, source, status, readout="hits"):
    return dict(
        schema="lumen-sensor-values/1",
        model="lumen:sensor",
        name=name,
        readout=readout,
        provenance=dict(source=source, status=status, fields={}, choices={}),
    )


class Sbnd:
    """sbndcode's, sbnd_data's and larsim's files, and the numbers read from them that more than one set uses."""

    def __init__(self, sbndcode, sbnd_data, larsim):
        root, self.data = Path(sbndcode), Path(sbnd_data)
        src = root / "source" / "sbndcode" / "OpDetSim"
        self.fcl = root / "fcl"
        self.pmt_alg, self.pmt_hh = Text(src / "DigiPMTSBNDAlg.cc"), Text(src / "DigiPMTSBNDAlg.hh")
        self.xa_alg, self.worker = Text(src / "DigiArapucaSBNDAlg.cc"), Text(src / "opDetDigitizerWorker.cc")
        phc = Text(Path(larsim) / "source" / "larsim" / "PhotonHitConverter" / "PhotonHitConverter_module.cc")
        split = r"> ([0-9.]+) \* CLHEP::eV"
        values = {float(m.group(1)) for _, m in phc.find(split)}
        if len(values) != 1:
            raise ValueError(f"PhotonHitConverter: {len(values)} energy splits {sorted(values)} (want 1)")
        self.split_ev = values.pop()
        self.split_cite = f"{LARSIM} larsim/PhotonHitConverter/" + phc.at(split)
        self.edges = [wavelength_of(self.split_ev)]  # nm, between the VUV band (below) and the visible one (above)
        m, ln = Text(self.fcl / "opticalproperties_sbnd.fcl").one(r"^\s*ScintPreScale:\s*([0-9.]+)")
        self.prescale, self.prescale_cite = float(m.group(1)), f"opticalproperties_sbnd.fcl:{ln}"

    def bands_note(self):
        return (f"the bands meet at {self.split_ev} eV ({self.edges[0]:.1f} nm), where larsim's PhotonHitConverter "
                f"files a photon as VUV (above the energy) or visible ({self.split_cite})")  # fmt: skip

    def vector(self, root_file, name):
        import uproot

        return np.asarray(list(uproot.open(self.data / "OpDetSim" / root_file)[name]), np.float64)

    def calibration(self):
        """The mean over the calibrated PMT channels of spe_amp_std / spe_amp, at the tag sbndcode's fcl names."""
        tags = Text(self.fcl / "calibration_database_PDS_TagSets_sbnd.fcl")
        (m, lt), (s, ls) = tags.one(r'PMTCalibrationDatabaseTag:\s*"(\w+)"'), tags.one(r"DatabaseTimeStamp:\s*(\d+)")
        tag, stamp = m.group(1), int(s.group(1)) // 10**9  # ns -> s, the iovs' unit
        db = self.data / "CalibrationDatabase" / "pds_calibration.db"
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        iov = c.execute("select i.iov_id from pds_calibration_iovs i join pds_calibration_tag_iovs t on "
                        "i.iov_id = t.iov_id where t.tag = ? and i.begin_time <= ? order by i.begin_time desc, "
                        "i.iov_id desc limit 1", (tag, stamp)).fetchone()[0]  # fmt: skip
        rows = np.asarray(c.execute("select reconstruct_channel, spe_amp, spe_amp_std from pds_calibration_data "
                                    "where __iov_id = ? order by channel", (iov,)).fetchall(), np.float64)  # fmt: skip
        rec = rows[:, 0] > 0
        rel = float(np.mean(rows[rec, 2] / rows[rec, 1]))
        cite = (f"{SBND_DATA} CalibrationDatabase/pds_calibration.db, table pds_calibration_data at tag {tag} (iov "
                f"{iov}; calibration_database_PDS_TagSets_sbnd.fcl:{lt}, {ls}): the mean of spe_amp_std / spe_amp "
                f"over its {int(rec.sum())} calibrated channels (reconstruct_channel)")  # fmt: skip
        return rel, cite


def sbnd_sets(s):
    """sbnd_pmt (coated) and sbnd_pmt_uncoated: digi_pmt_sbnd.fcl, DigiPMTSBNDAlg and sbnd_data. QE: sbndcode's two
    detection efficiencies per real photon, one per band (VUV below the split energy's wavelength, visible above)."""
    keys = ("PMTRiseTime", "PMTFallTime", "PMTMeanAmplitude", "TransitTime", "PMTChargeToADC", "TTS", "CableTime",
            "PMTBaseline", "PMTBaselineRMS", "PMTDarkNoiseRate", "PMTCoatedVUVEff_tpc0", "PMTCoatedVISEff_tpc0",
            "PMTUncoatedEff_tpc0")  # fmt: skip
    f = fcl_values(s.fcl / "digi_pmt_sbnd.fcl", keys)
    ln = {k: f"digi_pmt_sbnd.fcl:{x[1]}" for k, x in f.items()}
    v = {k: x[0] for k, x in f.items()}
    clock, lc = fcl_values(s.fcl / "detectorclocks_sbnd.fcl", ("ClockSpeedOptical",))["ClockSpeedOptical"]
    alg = s.pmt_alg
    m, lw = alg.one(r"sigma1 = fParams\.PMTRiseTime / \(std::sqrt\(([0-9.]+)\) \* \(std::sqrt\(-std::log\("
                    r"([0-9.]+)\)\) - std::sqrt\(-std::log\(([0-9.]+)\)\)\)\)")  # fmt: skip
    a, lo, hi = (float(x) for x in m.groups())
    width = np.sqrt(a) * (np.sqrt(-np.log(lo)) - np.sqrt(-np.log(hi)))  # the 10-90 % time of a half-Gaussian / sigma
    w_note = f"sqrt({m.group(1)}) (sqrt(-ln {m.group(2)}) - sqrt(-ln {m.group(3)}))"
    m, lf = s.pmt_hh.one(r"transitTimeSpread_frac = ([0-9.]+) \* std::sqrt\(([0-9.]+) \* std::log\(([0-9.]+)\)\)")
    fwhm = float(m.group(1)) * np.sqrt(float(m.group(2)) * np.log(float(m.group(3))))
    f_note = f"{m.group(1)} sqrt({m.group(2)} ln {m.group(3)}) (DigiPMTSBNDAlg.hh:{lf})"
    rel, rel_cite = s.calibration()
    tpb = s.vector("digi_pmt_sbnd_v2int0.root", "timeTPB")
    cites = dict(
        eff_div=alg.at(r"Eff_tpc0\(fParams\.PMT\w+Eff_tpc0\s*/\s*fParams\.larProp->ScintPreScale\(\)\)"),
        coated=alg.at(r"_PMTCoated(VUV|VIS)Eff = |< _PMTCoated(VUV|VIS)Eff"),
        uncoated=alg.at(r"_PMTUncoatedEff = |< _PMTUncoatedEff"),
        worker=s.worker.at(r"Reflected.*pdtype == .pmt_uncoated."),
        cable=alg.at(r"\+ fParams\.CableTime;"),
        tpb=alg.at(r"ttpb = fTimeTPB->fire\(\)"),
        clock=alg.at(r"params\.frequency = clockData\.OpticalClock"),
    )
    per_real = (f"per real photon: sbndcode divides each by ScintPreScale ({cites['eff_div']}) and applies it to the "
                f"photons Geant4 tracked, ScintYield x ScintPreScale per MeV; ScintPreScale is {s.prescale} "
                f"({s.prescale_cite}), set equal to the largest efficiency (the coated tube's VUV one), so that "
                "efficiency becomes 1 per tracked photon")  # fmt: skip
    out = {}
    for name, eff in (
        ("sbnd_pmt", (v["PMTCoatedVUVEff_tpc0"], v["PMTCoatedVISEff_tpc0"])),
        ("sbnd_pmt_uncoated", (0.0, v["PMTUncoatedEff_tpc0"])),
    ):
        d = base(name, SBND_REF, "transcribed", readout="waveform")
        d.update(qe=dict(band_edges_nm=list(s.edges), values=[float(x) for x in eff]), ce=None, efficiency=1.0,
                 t_offset_ns=v["CableTime"], tts=dict(form="gaussian", sigma_ns=round(v["TTS"] / fwhm, 8)),
                 delay=dict(form="table", edges_ns=list(range(len(tpb) + 1)), pdf=[float(x) for x in tpb]),
                 charge=dict(form="gauss_exp", sigma_pe=round(rel, 6), fraction=0.0, tau_pe=1.0),
                 gain=round(v["PMTChargeToADC"] * v["PMTMeanAmplitude"], 6), threshold=None,
                 pulse=dict(form="bigauss", t_peak_ns=v["TransitTime"],
                            sigma_rise_ns=round(v["PMTRiseTime"] / width, 6),
                            sigma_fall_ns=round(v["PMTFallTime"] / width, 6)),
                 dark_rate_hz=v["PMTDarkNoiseRate"],
                 frontend=dict(sampling_ns=round(1e3 / clock, 6), unit="ADC", baseline=v["PMTBaseline"],
                               noise=v["PMTBaselineRMS"], window_ns=0.0, charge_noise_pe=0.0, charge_scale=1.0,
                               charge_step_pe=0.25, charge_max_pe=64.0),
                 ranges={"t_offset": [-10.0, 10.0], "pulse/t_peak": [40.0, 70.0],
                         "pulse/sigma_rise": [0.5, 3.0], "pulse/sigma_fall": [2.0, 12.0]})  # fmt: skip
        if name == "sbnd_pmt":
            eff_lines = f"{ln['PMTCoatedVUVEff_tpc0']}, {ln['PMTCoatedVISEff_tpc0']}"
            how = ("a coated tube: PMTCoatedVUVEff on direct (VUV) light below the edge, PMTCoatedVISEff on reflected "
                   f"(visible) light above ({cites['coated']})")  # fmt: skip
        else:
            eff_lines = ln["PMTUncoatedEff_tpc0"]
            how = (f"an uncoated tube reads only reflected (visible) light ({cites['worker']}): 0 below the edge, "
                   f"PMTUncoatedEff above ({cites['uncoated']})")  # fmt: skip
        d["provenance"]["fields"] = {
            "qe": f"{eff_lines}: sbndcode's detection efficiencies, {per_real}; {how}; {s.bands_note()}",
            "t_offset_ns": f"{ln['CableTime']}: CableTime, added to every photon's time ({cites['cable']})",
            "tts": f"{ln['TTS']}: TTS, a FWHM; Gaussian sigma = FWHM / {f_note}",
            "delay": f"{SBND_DATA} OpDetSim/digi_pmt_sbnd_v2int0.root timeTPB (digi_pmt_sbnd.fcl PMTDataFile): the "
            f"TPB emission time in 1 ns bins, drawn for every PMT photon ({cites['tpb']})",
            "charge": f"{rel_cite}: PMTGaussianGainFluctuation, N(1, (spe_amp_std / spe_amp)^2) per photoelectron",
            "gain": f"{ln['PMTChargeToADC']} x {ln['PMTMeanAmplitude']}: ADC at the single photoelectron's peak",
            "pulse": f"{ln['TransitTime']}, {ln['PMTRiseTime']}, {ln['PMTFallTime']}: the ideal single "
            "photoelectron, two half-Gaussians about the transit time, each sigma its 10-90 % time / "
            f"{w_note} (DigiPMTSBNDAlg.cc:{lw}, {lw + 1})",
            "dark_rate_hz": ln["PMTDarkNoiseRate"],
            "frontend/sampling_ns": f"detectorclocks_sbnd.fcl:{lc}: the optical clock, {clock:g} MHz "
            f"({cites['clock']})",
            "frontend/baseline": ln["PMTBaseline"],
            "frontend/noise": ln["PMTBaselineRMS"],
        }
        d["provenance"]["choices"] = {
            **CHOICES,
            "charge/fraction": "0: sbndcode's gain fluctuation is Gaussian only (no exponential part)",
            "charge/tau_pe": "1: unused at fraction 0",
            "frontend/charge_max_pe": "64: the charge histogram's top",
            "ranges": RANGES_CHOICE,
        }
        d["provenance"]["warning"] = ("sbndcode v10_26_00 adds the TPB time in [0, 1) ns (CLHEP::RandGeneral of the "
                                      "table); this set uses the table in ns; production SPE shapes and gains are "
                                      "per-channel calibrations, not these defaults")  # fmt: skip
        out[name] = d
    return out


XA_EXP_TAILS = 10  # the exponential's table spans 10 decay times (the mass beyond, e^-10, is renormalised away)


def xarapuca_sets(s):
    """sbnd_xarapuca_vuv and sbnd_xarapuca_vis: digi_arapuca_sbnd.fcl, DigiArapucaSBNDAlg and sbnd_data. A VUV
    X-ARAPUCA reads direct (VUV) and reflected (TPB-shifted) light, a visible one reflected light only."""
    keys = ("ArapucaBaselineRMS", "ArapucaDarkNoiseRate", "CrossTalk", "ArapucaBaseline", "ArapucaMeanAmplitude",
            "XArapucaVUVEffVUV", "XArapucaVUVEffVis", "XArapucaVISEff", "DecayTXArapucaVIS", "DaphneFrequency",
            "AmpFluctuation")  # fmt: skip
    f = fcl_values(s.fcl / "digi_arapuca_sbnd.fcl", keys)
    ln = {k: f"digi_arapuca_sbnd.fcl:{x[1]}" for k, x in f.items()}
    v = {k: x[0] for k, x in f.items()}
    vuv_t, tpb = s.vector("digi_arapuca_sbnd.root", "TimeXArapucaVUV"), s.vector("digi_arapuca_sbnd.root", "timeTPB")
    tau = v["DecayTXArapucaVIS"]
    k = np.arange(int(np.ceil(XA_EXP_TAILS * tau)) + 1)
    expo = np.exp(-k[:-1] / tau) - np.exp(-k[1:] / tau)  # the exponential's mass per 1 ns bin
    vuv_tts = dict(form="table", edges_ns=list(range(len(vuv_t) + 1)), pdf=(vuv_t / vuv_t.sum()).round(9).tolist())
    vis_tts = dict(form="table", edges_ns=[int(x) for x in k], pdf=(expo / expo.sum()).round(9).tolist())
    vis_delay = dict(form="table", edges_ns=list(range(len(tpb) + 1)), pdf=[float(x) for x in tpb])
    xa = s.xa_alg
    cites = dict(
        vuv=xa.at(r"fTimeXArapucaVUV->fire\(\)"),
        vis=xa.at(r"fExponentialGen\.fire\(fParams\.DecayTXArapucaVIS\)"),
        div=xa.at(r"/ fParams\.larProp->ScintPreScale"),
        worker=s.worker.at(r"pdtype == .xarapuca_(vuv|vis)."),
        aux=xa.at(r"auxphotons\[j\]\.Time \+ fTimeTPB->fire\(\)"),
    )
    timing = {
        "sbnd_xarapuca_vuv": (vuv_tts, None, f"{SBND_DATA} OpDetSim/digi_arapuca_sbnd.root TimeXArapucaVUV: the "
                              f"photon time inside the VUV box, read in 1 ns bins, on direct light ({cites['vuv']})"),
        "sbnd_xarapuca_vis": (vis_tts, vis_delay, f"{ln['DecayTXArapucaVIS']}: the WLS bar's exponential decay ({tau} "
                              f"ns) in 1 ns bins over {XA_EXP_TAILS} decay times, then {SBND_DATA} "
                              "OpDetSim/digi_arapuca_sbnd.root timeTPB (the TPB emission time, read in 1 ns bins) as "
                              f"the delay ({cites['vis']})"),
    }  # fmt: skip
    per_real = (f"per real photon: sbndcode divides each by ScintPreScale ({cites['div']}) and applies it to the "
                "photons Geant4 tracked")  # fmt: skip
    out = {}
    for name, eff in (
        ("sbnd_xarapuca_vuv", (v["XArapucaVUVEffVUV"], v["XArapucaVUVEffVis"])),
        ("sbnd_xarapuca_vis", (0.0, v["XArapucaVISEff"])),
    ):
        tts, delay, tnote = timing[name]
        d = base(name, SBND_REF, "transcribed", readout="hits")
        d.update(qe=dict(band_edges_nm=list(s.edges), values=list(eff)), ce=None, efficiency=1.0, t_offset_ns=0.0,
                 tts=tts, **({"delay": delay} if delay else {}),
                 charge=dict(form="gauss_exp", sigma_pe=v["AmpFluctuation"], fraction=0.0, tau_pe=1.0),
                 gain=v["ArapucaMeanAmplitude"], threshold=None, dark_rate_hz=v["ArapucaDarkNoiseRate"],
                 frontend=dict(sampling_ns=round(1e3 / v["DaphneFrequency"], 6), unit="ADC",
                               baseline=v["ArapucaBaseline"], noise=v["ArapucaBaselineRMS"], window_ns=0.0,
                               charge_noise_pe=0.0, charge_scale=1.0, charge_step_pe=0.25, charge_max_pe=64.0),
                 ranges={"t_offset": [-10.0, 10.0]})  # fmt: skip
        if name == "sbnd_xarapuca_vuv":
            eff_lines, read = f"{ln['XArapucaVUVEffVUV']}, {ln['XArapucaVUVEffVis']}", "direct (VUV) light below the "
            read += "edge, reflected (visible) light above"
        else:
            eff_lines, read = ln["XArapucaVISEff"], "reflected (visible) light only: 0 below the edge"
        d["provenance"]["fields"] = {
            "qe": f"{eff_lines}: sbndcode's detection efficiencies, {per_real}; it reads {read} ({cites['worker']}); "
            f"{s.bands_note()}",
            "tts": tnote,
            **({"delay": tnote} if delay else {}),
            "charge": f"{ln['AmpFluctuation']}: N(1, {v['AmpFluctuation']}^2) per photoelectron",
            "gain": f"{ln['ArapucaMeanAmplitude']}: ADC at the single photoelectron's peak",
            "dark_rate_hz": ln["ArapucaDarkNoiseRate"],
            "frontend/sampling_ns": f"{ln['DaphneFrequency']}: the DAPHNE sampling ({v['DaphneFrequency']:g} MHz)",
            "frontend/baseline": ln["ArapucaBaseline"],
            "frontend/noise": ln["ArapucaBaselineRMS"],
        }
        d["provenance"]["choices"] = {
            **CHOICES,
            "t_offset_ns": "0: sbndcode adds no transit or cable delay to an X-ARAPUCA photon",
            "charge/fraction": "0: sbndcode's amplitude fluctuation is Gaussian only (no exponential part)",
            "charge/tau_pe": "1: unused at fraction 0",
            "frontend/charge_max_pe": "64: the charge histogram's top",
            "ranges": RANGES_CHOICE,
        }
        d["provenance"]["warning"] = (
            "sbndcode v10_26_00 draws the time tables with CLHEP::RandGeneral, in [0, 1) ns; this set reads them in 1 "
            f"ns bins, as sbnd_pmt does timeTPB. Not modelled: the SiPM cross-talk ({ln['CrossTalk']}: "
            f"{v['CrossTalk']} of photoelectrons count twice) and the DAPHNE waveform (readout hits)"
            + ("; the visible light a VUV X-ARAPUCA reads is timed with TimeXArapucaVUV, where sbndcode adds timeTPB "
               f"({cites['aux']})" if name == "sbnd_xarapuca_vuv" else "")
        )  # fmt: skip
        out[name] = d
    return out


def microboone_set(fcl, chconfig):
    """microboone_qe: MicroBooNE's QE on every PMT channel (pmtconfig_microboone.fcl), per real photon."""
    tokens, a, b = fcl_array(fcl, "QE")
    qe = {float(t) for t in tokens if float(t) != 1.0}  # the logic channels carry 1 (dummy)
    if len(qe) != 1:
        raise ValueError(f"pmtconfig_microboone.fcl QE: {sorted(qe)} on the PMT channels (want one value)")
    div = Text(chconfig).at(r"tmp_float_params\.at\( kQE \)\[i\] /=\s*LarProp->ScintPreScale\(\)")
    d = base("microboone_qe", f"{UBEVT} ({github(UBEVT)}): ubevt/Utilities/pmtconfig_microboone.fcl; {UBSIM} "
             f"({github(UBSIM)}): ubsim/OpticalDetectorSim/UBOpticalChConfig.cc", "transcribed",
             readout="pe")  # fmt: skip
    d.update(
        qe=dict(band_edges_nm=[], values=[qe.pop()]),  # one QE at every wavelength
        ce=None,
        efficiency=1.0,
        t_offset_ns=0.0,
        tts=None,
        charge=None,
        gain=1.0,
        threshold=None,
        dark_rate_hz=0.0,
        frontend=dict(sampling_ns=1.0, unit="pe", window_ns=0.0, charge_step_pe=0.25, charge_max_pe=4.0),
    )
    d["provenance"]["fields"] = {
        "qe": f"pmtconfig_microboone.fcl:{a}-{b}: QE, one value on every PMT channel (its logic channels carry 1); "
        f"per real photon: ubsim divides it by ScintPreScale before applying it to the tracked photons ({div})",
    }
    d["provenance"]["choices"] = {
        "efficiency": CHOICES["efficiency"],
        "t_offset_ns": "0: readout pe has no time",
        "gain": "1: readout pe counts photoelectrons",
        "dark_rate_hz": "0: readout pe counts photoelectrons from light only",
        "frontend/sampling_ns": "1: unused by readout pe",
        "frontend/window_ns": CHOICES["frontend/window_ns"],
        "frontend/charge_step_pe": CHOICES["frontend/charge_step_pe"],
        "frontend/charge_max_pe": "4: the charge histogram's top",
    }
    return d


# larproperties.fcl's scintillation constants an experiment's fcl may override: fcl key -> the tables' entry (a
# particle's yield or fast share: per_particle.<particle>.<field>)
PARTICLES = ("Muon", "Pion", "Electron", "Kaon", "Proton", "Alpha")
SCINT_OVERRIDES = {"ScintYield": "scint_yield", "ScintFastTimeConst": "fast_time_constant",
                   "ScintSlowTimeConst": "slow_time_constant", "ScintYieldRatio": "yield_ratio",
                   "ScintByParticleType": "by_particle_type"} | {
    f"{k}{s}": f"per_particle.{k}.{f}" for k in PARTICLES
    for s, f in (("ScintYield", "yield_per_MeV"), ("ScintYieldRatio", "fast_fraction"))}  # fmt: skip


def scint_overrides(fcl, src, table):
    """{entry: {value, source}} of each of SCINT_OVERRIDES the experiment's fcl table ``table`` sets, each with its
    line: the first line of the key inside ``table: { ... }``, or written ``table.KEY: value``; ``src`` names the
    file. A table set as ``@local::standard_properties`` alone overrides nothing."""  # noqa: D205, D209
    out, depth = {}, 0
    for i, ln in enumerate(Path(fcl).read_text().splitlines(), 1):
        code = ln.split("#")[0]
        if depth == 0:
            key = re.match(rf"\s*{table}\.(\w+):\s*([-+0-9.eE]+|true|false)\b", code)
            if re.match(rf"\s*{table}\s*:\s*{{", code):
                depth = code.count("{") - code.count("}")
                continue
        else:
            key = re.match(r"\s*(\w+):\s*([-+0-9.eE]+|true|false)\b", code) if depth == 1 else None
            depth += code.count("{") - code.count("}")
        if key and key.group(1) in SCINT_OVERRIDES and SCINT_OVERRIDES[key.group(1)] not in out:
            v = key.group(2)
            out[SCINT_OVERRIDES[key.group(1)]] = dict(value=(v == "true") if v in ("true", "false") else float(v),
                                                      source=f"{src}:{i} ({key.group(1)})")  # fmt: skip
    return out


def experiment_record(name, fcl):
    """The record ``lar.<name>`` of the tables: the experiment's fcl overrides of standard_properties, each with its
    line (``EXPERIMENTS``)."""  # noqa: D205, D209
    src, table = EXPERIMENTS[name]
    if not any(re.match(rf"\s*{table}\s*[:.]", ln) for ln in Path(fcl).read_text().splitlines()):
        raise ValueError(f"{fcl}: no fcl table {table!r} ({name})")
    over = scint_overrides(fcl, src, table)
    note = f"{table}' scintillation constants over standard_properties'" + ("" if over else " (none)")
    return {"source": src, "table": table, "overrides": over, "note": note}


def optics_tables(fcl, experiments=None):
    """LArSoft's standard LAr tables (RINDEX, RAYLEIGH, ABSLENGTH), its scintillation (ScintYield, the fast and slow
    spectra and time constants, ScintYieldRatio, ScintByParticleType, the per-particle yields and fast shares) and its
    ReflectiveSurfaces (what lumen_tpc reads) from lardataalg's larproperties.fcl, each with its lines;
    ``experiments``: {name: fcl} of EXPERIMENTS, each experiment's scintillation overrides written as ``lar.<name>``."""
    src = f"{LARDATAALG} lardataalg/DetectorInfo/larproperties.fcl"

    def table(ekey, vkey, unit, note):
        e, ea, eb = fcl_array(fcl, ekey)
        v, va, vb = fcl_array(fcl, vkey)
        if len(e) != len(v):
            raise ValueError(f"larproperties.fcl {ekey}/{vkey}: {len(e)} energies, {len(v)} values")
        return dict(energy=[number(x) for x in e], energy_unit="eV", values=[number(x) for x in v], value_unit=unit,
                    source=f"{src}:{min(ea, va)}-{max(eb, vb)} ({ekey}, {vkey})", note=note)  # fmt: skip

    yv, yl = fcl_values(fcl, ("ScintYield",))["ScintYield"]
    tc = fcl_values(fcl, ("ScintFastTimeConst", "ScintSlowTimeConst"))
    rv, rl = fcl_values(fcl, ("ScintYieldRatio",))["ScintYieldRatio"]
    bp, bl = Text(fcl).one(r"^\s*ScintByParticleType:\s*(true|false)\b")
    kinds = PARTICLES
    pp = fcl_values(fcl, tuple(f"{k}{s}" for k in kinds for s in ("ScintYield", "ScintYieldRatio")))
    per_particle = {k: dict(yield_per_MeV=pp[f"{k}ScintYield"][0], fast_fraction=pp[f"{k}ScintYieldRatio"][0],
                            source=f"{src}:{pp[f'{k}ScintYield'][1]}, {pp[f'{k}ScintYieldRatio'][1]} ({k}ScintYield, "
                            f"{k}ScintYieldRatio)") for k in kinds}  # fmt: skip
    names, na, _ = fcl_array(fcl, "ReflectiveSurfaceNames")
    energies, ea, _ = fcl_array(fcl, "ReflectiveSurfaceEnergies")
    refl, _, rb = fcl_array(fcl, "ReflectiveSurfaceReflectances")
    diff, _, db = fcl_array(fcl, "ReflectiveSurfaceDiffuseFractions")
    surfaces = {n.strip('"'): dict(reflectance=[number(x) for x in r], diffuse_fraction=[number(x) for x in f])
                for n, r, f in zip(names, refl, diff, strict=True)}  # fmt: skip
    out = {
        "meta": {
            "title": "LArSoft's standard liquid-argon optics (lardataalg standard_properties), as lumen_tpc "
            "reads them",
            "source": f"{src} ({github(LARDATAALG)})",
            "written_by": "tools/transcribe.py --lardataalg (every value parsed from the source, its lines in source)",
            "interpolation": "Geant4 G4MaterialPropertyVector::Value: linear in energy, held at the end values",
        },
        "lar": {
            "larsoft_standard": {
                "source": src,
                "rindex": table("RIndexEnergies", "RIndexSpectrum", "1", "RIndexSpectrum; the fcl cites "
                                "arXiv:2002.09346 (Babicz et al. 2020)"),
                "rayleigh_length": table("RayleighEnergies", "RayleighSpectrum", "cm", "RayleighSpectrum at 90 K, "
                                         "from arXiv:2002.09346; Geant4's RAYLEIGH"),
                "abs_length": table("AbsLengthEnergies", "AbsLengthSpectrum", "cm", "AbsLengthSpectrum; Geant4's "
                                    "ABSLENGTH"),
                "scint_yield": dict(value=yv, unit="photons/MeV", source=f"{src}:{yl} (ScintYield)",
                                    note="the physical yield; Geant4's SCINTILLATIONYIELD is ScintYield x "
                                    "ScintPreScale"),
                "fast_scint_spectrum": table("FastScintEnergies", "FastScintSpectrum", "relative",
                                             "FastScintSpectrum; Geant4's SCINTILLATIONCOMPONENT1"),
                "slow_scint_spectrum": table("SlowScintEnergies", "SlowScintSpectrum", "relative",
                                             "SlowScintSpectrum; Geant4's SCINTILLATIONCOMPONENT2"),
                "fast_time_constant": dict(value=tc["ScintFastTimeConst"][0], unit="ns",
                                           source=f"{src}:{tc['ScintFastTimeConst'][1]} (ScintFastTimeConst)"),
                "slow_time_constant": dict(value=tc["ScintSlowTimeConst"][0], unit="ns",
                                           source=f"{src}:{tc['ScintSlowTimeConst'][1]} (ScintSlowTimeConst)"),
                "yield_ratio": dict(value=rv, source=f"{src}:{rl} (ScintYieldRatio)",
                                    note="the fast share of the light when ScintByParticleType is false"),
                "by_particle_type": dict(value=bp.group(1) == "true", source=f"{src}:{bl} (ScintByParticleType)",
                                         note="true: each particle's yield and fast share (per_particle) in place "
                                         "of ScintYield and ScintYieldRatio"),
                "per_particle": per_particle,
            }
        },
        "surfaces": {
            "larsoft_standard": {
                "source": f"{src}:{min(na, ea)}-{max(rb, db)} (ReflectiveSurfaceEnergies, Names, Reflectances, "
                "DiffuseFractions)",
                "energies_eV": [number(x) for x in energies],
                "surfaces": surfaces,
                "used_by": "MicroBooNE (larproperties_microboone.fcl is standard_properties)",
            }
        },
    }  # fmt: skip
    for name, path in sorted((experiments or {}).items()):
        out["lar"][name] = experiment_record(name, path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="the value sets' directory (with the sources below)")
    ap.add_argument("--optics", required=True, help="the LArSoft optics tables JSON to write")
    ap.add_argument("--lardataalg", required=True)
    ap.add_argument(
        "--fcl",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help=f"an experiment's fcl over standard_properties, NAME one of {sorted(EXPERIMENTS)}",
    )
    for k in ("sbndcode", "sbnd-data", "larsim", "ubevt", "ubsim"):
        ap.add_argument(f"--{k}")
    a = ap.parse_args()
    fcls = dict(x.split("=", 1) for x in a.fcl)
    if set(fcls) - set(EXPERIMENTS):
        ap.error(f"--fcl: unknown experiments {sorted(set(fcls) - set(EXPERIMENTS))}")
    if a.out:
        missing = [k for k in ("sbndcode", "sbnd_data", "larsim", "ubevt", "ubsim") if getattr(a, k) is None]
        if missing:
            ap.error(f"--out needs {missing}")
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        s = Sbnd(a.sbndcode, a.sbnd_data, a.larsim)
        sets = dict(sbnd_sets(s))
        sets.update(xarapuca_sets(s))
        sets["microboone_qe"] = microboone_set(a.ubevt, a.ubsim)
        for name, d in sets.items():
            (out / f"{name}.json").write_text(json.dumps(d, indent=1) + "\n")
        fcls.setdefault("sbnd", str(s.fcl / "opticalproperties_sbnd.fcl"))
        print("wrote", sorted(sets))
    if set(fcls) != set(EXPERIMENTS):
        ap.error(f"--fcl: every experiment's fcl is needed; missing {sorted(set(EXPERIMENTS) - set(fcls))}")
    Path(a.optics).write_text(json.dumps(optics_tables(a.lardataalg, fcls), indent=1) + "\n")
    print("wrote", a.optics)


if __name__ == "__main__":
    main()
