# Core and Registry orchestration v0.1

AIPE Design Agent is moving incrementally toward engineering orchestration.
The existing `pea` package, calculators, optimiser, desktop app and UI remain
available. The additive offline path is:

```
Core Engineering State -> validated Registry index -> suitability/fidelity gates
 -> auditable capability plan -> explicit local adapter -> new state evidence
 -> engineering review
```

## Minimal open-source path

Python 3.10+ is recommended for the coordinated ecosystem. The new path needs only
the dependencies below, with local Core and Registry checkouts. It does not need
OpenAI, an API key, LangChain, a proprietary solver or the full existing UI stack.

```sh
python -m pip install -r requirements-orchestration.txt
python -m pea.orchestration --help
python -m pea.orchestration \
  --state ../AIPE-Core/examples/dab-10kw/engineering-state.json \
  --core ../AIPE-Core \
  --registry ../AIPE-Registry/generated/aipe.json \
  --registry-schema ../AIPE-Registry/schema/capability-manifest.schema.json \
  --assessments examples/ecosystem/assessments.json \
  --capability operating-point-analysis --platform linux --installed python \
  --fidelity analytical --output out/plan.json
```

Use `--platform windows` or `macos` on those platforms. `--installed` is the user's
explicit inventory of available tools, not a claim that discovery probed the OS.
For this same selection, append `--execute-local --created-at 2026-10-07T00:00:00Z`
and choose `--output out/state.json` to execute the built-in nominal operating-point
adapter. Supply the actual run timestamp for real work. The timestamp is explicit
so tests/examples can reproduce their output. No external command is read from a
manifest or executed.

The synthetic Core DAB example requests 10 kW, 800 V to 400 V at 100 kHz. The adapter
only derives 25 A nominal DC output current and a 0.5 voltage ratio. It makes no
transformer turns-ratio, device, leakage-inductance, current-waveform, ZVS,
efficiency or measured-performance claim. These two numbers describe requested
ratings; they are not an implemented converter design.

## Capability selection

The Registry manifest and tool must both declare the requested capability. Each
candidate also needs a reviewed assessment with exactly:

```json
{"capability_id":"aipe.example","tool_id":"example","capability":"switching-circuit-simulation","suitability":1.0,"fidelities":["switching-waveform"],"rationale":"Describe the model, operating range and limitations."}
```

Unassessed, unavailable, unsupported-platform, deprecated/planned, insufficiently
validated or wrong-fidelity paths are rejected with reasons. Suitability is a
finite score in [0,1], scoped to the exact capability; zero excludes a candidate.
Fidelity labels are explicit assessed capabilities, not an assumed universal
low-to-high hierarchy. A thermal FEA solver is not automatically a switching
converter simulator.

Among eligible candidates, sort by suitability, integration-validation level,
explicit user preference, then licence accessibility (open source first), with
stable ID tie-breaks. `--preferred plecs` can select a professional's existing
licence among equally suitable and validated paths. A higher-quality commercial
path is not demoted below an unsuitable open tool. Assessed alternatives retain
their limitations. No suitable candidate produces an audit plan and exit code 2.

## State and provenance boundaries

`pea.state` runs the canonical `scripts/validate.py` module from the explicitly
supplied local Core checkout. This executes that checkout's Python validator, so
review and pin the Core source just like a library dependency. Core resolves
logical schemas from disk with remote resolution disabled and checks evidence
references/cycles, entity uniqueness, simulation records and validation claims.
`pea.registry` validates the complete index against the supplied Registry
manifest schema and rejects duplicate IDs/unknown dependencies. Keep those checkouts
pinned/reviewed together; validators do not establish a remote release exists.
The same authoritative Core semantic checks can be run independently:

```sh
python ../AIPE-Core/scripts/validate.py out/state.json
```

`pea.adapters` copies the input, adds `extensions.aipe.design-agent`, appends
`kind: analytical` evidence, and keeps prior evidence and physical validation
unchanged. Its attribution and input evidence references make the calculation
traceable. The existing PEA calculators use their historical units/APIs and are
not silently redefined as Core-compatible adapters. Outputs from those calculators
must be independently reviewed, unit-mapped and evidence-linked before import.

v0.1 runs the single audited adapter only. General tool dispatch, solver sandboxes,
credential/licence management, automated model suitability assessment and device
database result ingestion remain future integration work.
