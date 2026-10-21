"""Thermal design evaluation for power semiconductors and their cooling (SI units).

Pure-Python package (no LangChain/Streamlit imports):

- ``pea.thermal.network`` -- steady-state junction -> case -> TIM -> shared heat
  sink -> ambient networks for several devices on one sink, Foster/Cauer
  transient impedances (standard library only);
- ``pea.thermal.electrothermal`` -- loss(Tj) <-> Tj fixed-point iteration with
  pluggable loss callables and datasheet-based defaults (standard library only);
- ``pea.thermal.cooling`` -- natural convection, forced air and liquid cold plate
  comparison; air models come from the corrected ``heatsink_model`` in the
  sibling HeatSinkOptimisation checkout (``HEATSINK_OPT_DIR`` or
  ``../HeatSinkOptimisation``), which needs numpy/scipy;
- ``pea.thermal.heatsink_optimisation`` -- Stage A analytical Pareto screening
  of plate-fin geometries with FEM-verification flags;
- ``pea.thermal.dab_case`` -- the AIPE 10 kW DAB case study inputs and assumptions;
- ``python -m pea.thermal`` -- JSON command-line interface.

Results are analytical correlation estimates with stated validity; none of them
is a CFD, FEM or measured value.
"""

from pea.thermal import electrothermal, network  # noqa: F401  (standard-library modules)

__all__ = ["network", "electrothermal"]
