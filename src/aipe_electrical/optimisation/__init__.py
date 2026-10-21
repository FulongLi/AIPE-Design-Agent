"""Multi-objective helpers (generic Pareto front and weighted ranking) and an SPS design-space sweep.

Only explicit models are used: the sweep evaluates the exact lossless SPS model of
:mod:`aipe_electrical.converters.dab_sps`. No loss, magnetic, thermal or cost model
is included; the former PEA Pareto optimiser with its fitted loss factors was not migrated.
"""

from aipe_electrical.optimisation import dab_sps_sweep, pareto

__all__ = ["dab_sps_sweep", "pareto"]
