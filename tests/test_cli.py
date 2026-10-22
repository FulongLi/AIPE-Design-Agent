"""Command-line interface (aipe_electrical.interfaces.cli) through ``main`` and the console script."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aipe_electrical import __version__
from aipe_electrical.interfaces.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "dab-10kw-sps.json"


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_design_reproduces_benchmark(capsys):
    code, out, _ = run(
        capsys,
        "dab-sps",
        "design",
        "--v1",
        "800",
        "--v2",
        "400",
        "--power",
        "10000",
        "--f-sw",
        "100e3",
        "--phi-deg",
        "22.5",
    )
    assert code == 0
    report = json.loads(out)
    assert report["series_inductance_total_uH"] == pytest.approx(35.0, rel=1e-9)
    assert report["series_current_rms_primary_A"] == pytest.approx(13.6775, abs=5e-5)


def test_analyse_from_example_file_with_output(capsys, tmp_path):
    target = tmp_path / "out" / "analysis.json"
    code, out, _ = run(capsys, "dab-sps", "analyse", "--input", str(EXAMPLE), "--output", str(target))
    assert code == 0 and out == ""
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["phase_shift_source"] == "solved for power_W"
    assert report["inputs"]["phase_shift_deg"]["value"] == pytest.approx(22.5, abs=1e-9)
    assert report["derived"]["max_power_sps"]["value"] == pytest.approx(22857.142857, rel=1e-9)


def test_flags_override_input_file(capsys):
    code, out, _ = run(capsys, "dab-sps", "analyse", "--input", str(EXAMPLE), "--power", "5000")
    assert code == 0
    assert json.loads(out)["derived"]["power"]["value"] == pytest.approx(5000.0)


def test_waveform_dcdc_and_losses(capsys):
    code, out, _ = run(capsys, "dab-sps", "waveform", "--input", str(EXAMPLE), "--samples", "8", "--origin", "centre")
    assert code == 0 and len(json.loads(out)["i_L_A"]) == 9
    code, out, _ = run(capsys, "dcdc", "boost", "--v-in", "5", "--v-out", "12", "--i-out", "1", "--f-sw", "100e3")
    assert code == 0 and json.loads(out)["duty"] == pytest.approx(7 / 12)
    code, out, _ = run(
        capsys,
        "buck-losses",
        "--v-in",
        "12",
        "--v-out",
        "5",
        "--i-out",
        "2",
        "--f-sw",
        "100e3",
        "--r-ds-on-high",
        "0.05",
        "--r-dcr",
        "0.03",
        "--t-rise",
        "20e-9",
        "--t-fall",
        "20e-9",
        "--v-f-diode",
        "0.5",
    )
    assert code == 0 and json.loads(out)["efficiency"] == pytest.approx(0.922963, abs=1e-6)


def test_invalid_phase_shift_exits_with_error(capsys):
    code, out, err = run(
        capsys,
        "dab-sps",
        "analyse",
        "--v1",
        "800",
        "--v2",
        "400",
        "--turns-ratio-np-ns",
        "2",
        "--f-sw",
        "100e3",
        "--l-series-total",
        "35e-6",
        "--phi-deg",
        "95",
    )
    assert code == 1 and out == "" and "pi/2" in err


def test_missing_phase_information_is_an_error(capsys):
    code, _, err = run(
        capsys,
        "dab-sps",
        "analyse",
        "--v1",
        "800",
        "--v2",
        "400",
        "--turns-ratio-np-ns",
        "2",
        "--f-sw",
        "100e3",
        "--l-series-total",
        "35e-6",
    )
    assert code == 1 and "exactly one of" in err


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_console_script_or_module_entry_point():
    exe = shutil.which("aipe-electrical")
    cmd = [exe] if exe else [sys.executable, "-m", "aipe_electrical.interfaces.cli"]
    result = subprocess.run(
        [*cmd, "dab-sps", "analyse", "--input", str(EXAMPLE)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["derived"]["power"]["value"] == pytest.approx(10000.0)
