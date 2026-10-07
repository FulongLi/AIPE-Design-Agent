"""Offline Registry planning plus one explicitly selected local analytical adapter."""
import argparse
import json
from pathlib import Path

from pea.adapters import analyse_operating_point
from pea.orchestration import select_capability
from pea.registry import load_registry
from pea.state import load_json, validate_state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', required=True, type=Path)
    parser.add_argument('--core', required=True, type=Path, help='local AIPE-Core checkout for offline schemas')
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--registry-schema', required=True, type=Path)
    parser.add_argument('--assessments', required=True, type=Path, help='reviewed suitability and fidelity assessments')
    parser.add_argument('--capability', required=True)
    parser.add_argument('--platform', choices=['linux', 'windows', 'macos'], required=True)
    parser.add_argument('--installed', nargs='+', default=['python'])
    parser.add_argument('--preferred', nargs='*', default=[])
    parser.add_argument('--fidelity', default='analytical')
    parser.add_argument('--minimum-validation', default='schema_validated', choices=['not_run', 'schema_validated', 'tested', 'measured'])
    parser.add_argument('--output', required=True, type=Path, help='plan JSON, or updated state with --execute-local')
    parser.add_argument('--execute-local', action='store_true', help='execute only the built-in operating-point-analysis adapter')
    parser.add_argument('--created-at', help='explicit ISO 8601 timestamp required for execution evidence')
    args = parser.parse_args(argv)
    try:
        state = validate_state(load_json(args.state), args.core)
        registry = load_registry(args.registry, args.registry_schema)
        plan = select_capability(registry, args.capability, load_json(args.assessments), args.installed, args.platform,
                                 args.fidelity, args.minimum_validation, args.preferred)
        output = plan
        if args.execute_local:
            chosen = plan['selected']
            if not chosen or (chosen['capability_id'], chosen['tool_id'], args.capability) != ('aipe.design-agent', 'python', 'operating-point-analysis'):
                raise ValueError('only the selected built-in operating-point-analysis adapter may execute; external paths remain plans')
            if not args.created_at:
                raise ValueError('--created-at is required for analytical provenance')
            output = analyse_operating_point(state, args.created_at)
            output['extensions']['aipe.design-agent']['selection'] = plan
            output['extensions']['aipe.design-agent']['selection']['execution'] = 'local_analysis_completed'
            validate_state(output, args.core)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
        if plan['selected'] is None:
            print('No suitable available capability; inspect the rejection reasons in the plan.')
            return 2
    except (ValueError, KeyError, OSError, TypeError) as exc:
        parser.exit(1, f'{exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
