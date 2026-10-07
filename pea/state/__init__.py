"""Offline Core schema validation for the additive orchestration path."""
import json
from pathlib import Path


def load_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f'duplicate JSON key: {key}')
            value[key] = item
        return value
    def reject(value):
        raise ValueError(f'nonfinite JSON number: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=reject)


def validate_state(state, core):
    """Run the canonical validator from an explicitly trusted local Core checkout.

    Core owns both schemas and semantic checks. Reusing its checker avoids a
    permissive, drifting partial implementation in every consumer. This loads
    local Python code: callers must review/pin the checkout supplied as `core`.
    """
    import importlib.util
    core = Path(core).resolve()
    script = core / 'scripts/validate.py'
    if not script.is_file() or not (core / 'schemas/engineering-state.schema.json').is_file():
        raise ValueError('trusted Core checkout must contain scripts/validate.py and schemas')
    spec = importlib.util.spec_from_file_location('_aipe_core_contract_validator', script)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    errors = checker.validate_state(state, core / 'schemas')
    if errors:
        raise ValueError('; '.join(errors))
    return state
