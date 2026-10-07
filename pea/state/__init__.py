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
    """Use a local Core checkout; never download schemas or execute its code."""
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
    from referencing.exceptions import NoSuchResource
    def offline(uri):
        raise NoSuchResource(ref=uri)
    schemas = [load_json(path) for path in sorted((Path(core) / 'schemas').glob('*.schema.json'))]
    if not schemas:
        raise ValueError('Core schema directory is missing or empty')
    resources = Registry(retrieve=offline).with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
    schema = next(s for s in schemas if s['$id'].endswith('/engineering-state.schema.json'))
    validator = Draft202012Validator(schema, registry=resources, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(state), key=lambda e: e.json_path)
    if errors:
        raise ValueError('; '.join(f'{e.json_path}: {e.message}' for e in errors))
    # Avoid silently consuming dangling or rejected evidence in an otherwise valid shape.
    evidence = {e['id']: e for e in state['evidence']}
    if len(evidence) != len(state['evidence']):
        raise ValueError('duplicate evidence IDs')
    def walk(value):
        if isinstance(value, dict):
            for reference in value.get('evidence_refs', []):
                if reference not in evidence or evidence[reference]['review_status'] == 'rejected':
                    raise ValueError(f'unknown or rejected evidence: {reference}')
            for key, item in value.items():
                if key != 'extensions':
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(state)
    return state
