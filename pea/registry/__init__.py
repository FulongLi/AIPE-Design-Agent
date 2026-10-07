"""Read Registry artifacts as data. Never import or execute manifest commands."""
from pathlib import Path
from pea.state import load_json


def load_registry(path, schema_path):
    from jsonschema import Draft202012Validator, FormatChecker
    payload = load_json(path)
    if not isinstance(payload, dict) or set(payload) != {'schema_version', 'capabilities'} or payload['schema_version'] != '0.1.0':
        raise ValueError('unsupported Registry envelope')
    if not isinstance(payload['capabilities'], list) or not payload['capabilities']:
        raise ValueError('Registry capabilities must be a nonempty list')
    checker = FormatChecker()
    if 'uri' not in checker.checkers:
        raise ValueError('URI format checker unavailable; install requirements-orchestration.txt')
    validator = Draft202012Validator(load_json(Path(schema_path)), format_checker=checker)
    ids = set()
    for manifest in payload['capabilities']:
        failures = list(validator.iter_errors(manifest))
        if failures:
            raise ValueError(f'invalid capability manifest: {failures[0].message}')
        if manifest['id'] in ids:
            raise ValueError(f'duplicate capability ID: {manifest["id"]}')
        ids.add(manifest['id'])
    for manifest in payload['capabilities']:
        for dependency in manifest['dependencies']:
            if dependency['id'] not in ids:
                raise ValueError(f'unknown dependency: {dependency["id"]}')
    return payload
