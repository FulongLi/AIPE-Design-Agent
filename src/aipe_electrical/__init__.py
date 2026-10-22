"""aipe_electrical: analytical electrical design models for the AIPE ecosystem.

Sub-packages
------------
- :mod:`aipe_electrical.converters` -- converter-level analytical models with
  explicit SI units and sign conventions (``dab_sps``: lossless single-phase-shift
  dual-active-bridge analysis).
- :mod:`aipe_electrical.analysis` -- waveform metrics, continuous-conduction
  DC-DC sizing formulas and a first-order buck loss estimate.
- :mod:`aipe_electrical.optimisation` -- generic Pareto helpers and an SPS
  design-space sweep built on the lossless model (screening only).
- :mod:`aipe_electrical.interfaces` -- JSON in/out helpers and the
  ``aipe-electrical`` command line.

Every quantity is in SI units unless the name carries an explicit unit suffix
(JSON keys such as ``series_inductance_total_uH``). All results are exact
consequences of the stated idealised models; none is a simulated or measured value.
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
