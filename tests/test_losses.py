"""First-order buck loss estimate (aipe_electrical.analysis.losses) against hand-derived values."""

import math

import pytest

from aipe_electrical.analysis import losses

BASE = dict(v_in=12.0, v_out=5.0, i_out=2.0, f_sw=100e3, r_ds_on_high=0.05, r_dcr=0.03, t_rise=20e-9, t_fall=20e-9)


def test_diode_rectifier_breakdown():
    r = losses.buck_first_order_losses(**BASE, v_f_diode=0.5)
    assert r.rectifier == "diode"
    assert r.duty == pytest.approx(5 / 12)
    assert r.high_side_conduction == pytest.approx(5 / 12 * 4 * 0.05)
    assert r.low_side_conduction == pytest.approx(0.5 * 2 * 7 / 12)
    assert r.inductor_conduction == pytest.approx(4 * 0.03)
    assert r.switching == pytest.approx(0.5 * 12 * 2 * 40e-9 * 1e5)
    assert r.total_loss == pytest.approx(
        r.high_side_conduction + r.low_side_conduction + r.inductor_conduction + r.switching
    )
    assert r.total_loss == pytest.approx(0.834667, abs=1e-6)
    assert r.efficiency == pytest.approx(10 / 10.834667, abs=1e-6)
    assert isinstance(r.to_dict()["assumptions"], tuple)


def test_synchronous_rectifier_is_more_efficient_here():
    diode = losses.buck_first_order_losses(**BASE, v_f_diode=0.5)
    sync = losses.buck_first_order_losses(**BASE, r_ds_on_low=0.05)
    assert sync.rectifier == "synchronous"
    assert sync.low_side_conduction == pytest.approx(7 / 12 * 4 * 0.05)
    assert sync.efficiency > diode.efficiency


def test_ripple_increases_conduction_loss_only():
    flat = losses.buck_first_order_losses(**BASE, v_f_diode=0.5)
    rippled = losses.buck_first_order_losses(**BASE, v_f_diode=0.5, ripple_current_pp=0.6)
    assert rippled.inductor_current_rms == pytest.approx(math.sqrt(4.03))
    assert rippled.high_side_conduction == pytest.approx(5 / 12 * 4.03 * 0.05)
    assert rippled.switching == flat.switching
    assert rippled.low_side_conduction == flat.low_side_conduction  # diode term uses the average current


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # no rectifier model
        {"v_f_diode": 0.5, "r_ds_on_low": 0.05},  # both
        {"v_f_diode": 0.5, "v_out": 12.0},  # not a buck
        {"v_f_diode": 0.5, "r_dcr": -0.01},
    ],
)
def test_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        losses.buck_first_order_losses(**{**BASE, **kwargs})
