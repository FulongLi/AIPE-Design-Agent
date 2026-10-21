"""CCM sizing formulas (aipe_electrical.analysis.dcdc) against hand-derived values.

Ported from the surviving legacy ``tests/test_calculator.py`` buck/boost/buck-boost/SEPIC/Cuk
checks, now in SI units with explicit expected numbers.
"""

import math

import pytest

from aipe_electrical.analysis import dcdc


def test_buck_12v_to_5v_2a():
    d = dcdc.buck_ccm(v_in=12, v_out=5, i_out=2, f_sw=100e3)
    assert d.topology == "buck" and d.output_polarity == "positive"
    assert d.duty == pytest.approx(5 / 12)
    (ind,) = d.inductors
    assert ind.inductance == pytest.approx(48.6111e-6, rel=1e-5)  # 5 * (7/12) / (1e5 * 0.6)
    assert ind.current_ripple_pp == pytest.approx(0.6)
    assert ind.current_peak == pytest.approx(2.3)
    assert ind.current_rms == pytest.approx(math.sqrt(4 + 0.36 / 12))
    (cap,) = d.capacitors
    assert cap.capacitance == pytest.approx(15e-6, rel=1e-12)  # 0.6 / (8 * 1e5 * 0.05)
    assert cap.voltage_ripple_pp == pytest.approx(0.05)
    assert isinstance(d.to_dict()["inductors"][0]["inductance"], float)


def test_buck_duty_formula_and_rejections():
    assert dcdc.buck_ccm(v_in=24, v_out=3.3, i_out=5, f_sw=200e3).duty == pytest.approx(3.3 / 24)
    with pytest.raises(ValueError):
        dcdc.buck_ccm(v_in=5, v_out=12, i_out=1, f_sw=100e3)
    with pytest.raises(ValueError):
        dcdc.buck_ccm(v_in=12, v_out=5, i_out=2, f_sw=0.0)
    with pytest.raises(ValueError):
        dcdc.buck_ccm(v_in=12, v_out=5, i_out=2, f_sw=100e3, ripple_current_fraction=1.0)


def test_boost_5v_to_12v_1a():
    d = dcdc.boost_ccm(v_in=5, v_out=12, i_out=1, f_sw=100e3)
    assert d.duty == pytest.approx(7 / 12)
    (ind,) = d.inductors
    assert ind.current_avg == pytest.approx(2.4)  # I_in = I_out V_out / V_in
    assert ind.current_ripple_pp == pytest.approx(0.72)
    assert ind.inductance == pytest.approx(5 * (7 / 12) / (1e5 * 0.72), rel=1e-12)
    (cap,) = d.capacitors
    assert cap.capacitance == pytest.approx(1 * (7 / 12) / (1e5 * 0.12), rel=1e-12)
    # volt-second balance: V_in D = (V_out - V_in)(1 - D)
    assert 5 * d.duty == pytest.approx((12 - 5) * (1 - d.duty))
    with pytest.raises(ValueError):
        dcdc.boost_ccm(v_in=12, v_out=5, i_out=1, f_sw=100e3)


def test_buck_boost_12v_to_minus_12v_1a():
    d = dcdc.buck_boost_ccm(v_in=12, v_out_magnitude=12, i_out=1, f_sw=100e3)
    assert d.output_polarity == "negative"
    assert d.duty == pytest.approx(0.5)
    (ind,) = d.inductors
    assert ind.current_avg == pytest.approx(2.0)  # I_out / (1 - D) = I_in + I_out
    assert ind.inductance == pytest.approx(100e-6, rel=1e-12)  # 12 * 0.5 / (1e5 * 0.6)
    (cap,) = d.capacitors
    assert cap.capacitance == pytest.approx(0.5 / (1e5 * 0.12), rel=1e-12)


def test_sepic_12v_to_5v_2a():
    d = dcdc.sepic_ccm(v_in=12, v_out=5, i_out=2, f_sw=100e3)
    assert d.duty == pytest.approx(5 / 17)
    l1, l2 = d.inductors
    assert (l1.name, l2.name) == ("L1", "L2")
    assert l1.current_avg == pytest.approx(2 * 5 / 12)
    assert l2.current_avg == pytest.approx(2.0)
    assert l1.inductance == pytest.approx(12 * (5 / 17) / (1e5 * 0.25), rel=1e-12)
    assert l2.inductance == pytest.approx(12 * (5 / 17) / (1e5 * 0.6), rel=1e-12)
    c_out, c_couple = d.capacitors
    assert c_out.capacitance == pytest.approx(2 * (5 / 17) / (1e5 * 0.05), rel=1e-12)
    assert c_couple.voltage_dc == pytest.approx(12.0)
    assert c_couple.capacitance == pytest.approx(2 * (5 / 17) / (1e5 * 0.6), rel=1e-12)
    assert dcdc.sepic_ccm(v_in=5, v_out=12, i_out=1, f_sw=100e3).duty > 0.5


def test_cuk_12v_to_minus_5v_2a():
    d = dcdc.cuk_ccm(v_in=12, v_out_magnitude=5, i_out=2, f_sw=100e3)
    assert d.output_polarity == "negative"
    assert d.duty == pytest.approx(5 / 17)
    l1, l2 = d.inductors
    assert l1.inductance == pytest.approx(12 * (5 / 17) / (1e5 * 0.25), rel=1e-12)
    # L2 from V_in D equals |V_out| (1 - D) by volt-second balance
    assert l2.inductance == pytest.approx(5 * (12 / 17) / (1e5 * 0.6), rel=1e-12)
    c_out, c_couple = d.capacitors
    assert c_out.capacitance == pytest.approx(0.6 / (8 * 1e5 * 0.05), rel=1e-12)
    assert c_couple.voltage_dc == pytest.approx(17.0)
    assert c_couple.capacitance == pytest.approx(2 * (5 / 17) / (1e5 * 0.85), rel=1e-12)
