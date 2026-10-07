"""Deterministic capability selection. Suitability is an explicit assessment."""
import math

VALIDATION = {'not_run': 0, 'schema_validated': 1, 'tested': 2, 'measured': 3}
ACCESS = {'open_source': 0, 'free_proprietary': 1, 'commercial': 2}


def select_capability(registry, capability, assessments, installed, platform,
                      fidelity='analytical', minimum_validation='schema_validated', preferred=()):
    """Return an auditable plan, without installing or executing external tools.

    Assessment keys are (capability_id, tool_id). Unassessed paths fail closed;
    neither tool names nor an open-source licence establish physical suitability.
    """
    if minimum_validation not in VALIDATION:
        raise ValueError('unknown minimum_validation')
    assessment_map = {}
    for assessment in assessments:
        required = {'capability_id', 'tool_id', 'capability', 'suitability', 'fidelities', 'rationale'}
        if not isinstance(assessment, dict) or set(assessment) != required:
            raise ValueError('assessment requires capability_id, tool_id, capability, suitability, fidelities, rationale')
        score = assessment['suitability']
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('suitability must be a finite number from 0 to 1')
        if not isinstance(assessment['fidelities'], list) or not all(isinstance(f, str) for f in assessment['fidelities']) or not assessment['rationale']:
            raise ValueError('assessment needs explicit fidelities and rationale')
        key = (assessment['capability_id'], assessment['tool_id'], assessment['capability'])
        if key in assessment_map:
            raise ValueError('duplicate suitability assessment')
        assessment_map[key] = assessment
    candidates, rejected = [], []
    preferred = list(preferred)
    for manifest in sorted(registry['capabilities'], key=lambda m: m['id']):
        if capability not in manifest['capabilities']:
            continue
        for tool in sorted(manifest['tools'], key=lambda t: t['id']):
            if capability not in tool['capabilities']:
                continue
            assessment = assessment_map.get((manifest['id'], tool['id'], capability))
            reasons = []
            if manifest['status'] not in {'active', 'experimental'}:
                reasons.append('repository is planned or deprecated')
            if not assessment or assessment['suitability'] <= 0:
                reasons.append('technical suitability has not been established')
            elif fidelity not in assessment['fidelities']:
                reasons.append('required fidelity is not supported by the assessment')
            if tool['id'] not in installed:
                reasons.append('tool is not declared installed/available')
            if platform not in tool['platforms']:
                reasons.append('platform is unsupported')
            level = VALIDATION[manifest['validation']['status']]
            if level < VALIDATION[minimum_validation]:
                reasons.append('integration validation status is below the requested minimum')
            identity = {'capability_id': manifest['id'], 'tool_id': tool['id']}
            if reasons:
                rejected.append({**identity, 'reasons': reasons})
                continue
            preference = preferred.index(tool['id']) if tool['id'] in preferred else len(preferred)
            rank = (-assessment['suitability'], -level, preference, ACCESS[tool['licence_class']], manifest['id'], tool['id'])
            candidates.append((rank, {**identity, 'repository': manifest['repository'], 'licence_class': tool['licence_class'],
                                     'integration_validation': manifest['validation']['status'], 'assessment': assessment,
                                     'limitations': tool['limitations'] + manifest['validation']['limitations']}))
    candidates.sort(key=lambda candidate: candidate[0])
    return {'schema_version': '0.1.0', 'capability': capability, 'required_fidelity': fidelity,
            'selected': candidates[0][1] if candidates else None,
            'alternatives': [candidate[1] for candidate in candidates[1:]], 'rejected': rejected,
            'execution': 'not_run', 'review_status': 'unreviewed',
            'policy': 'Suitability, integration validation, explicit preference, licence accessibility; availability/platform/fidelity are mandatory gates.'}
