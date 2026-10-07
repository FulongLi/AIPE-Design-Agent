"""Explicit local analytical adapters; no manifest-driven code execution."""
import copy
import datetime as dt
import math


def analyse_operating_point(state, created_at, evidence_id='evidence.operating-point-analysis'):
    """Derive P/V and voltage ratio only, preserving all existing design choices."""
    if state.get('schema_version') != '0.1.0':
        raise ValueError('Engineering State 0.1.0 is required')
    timestamp = dt.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('created_at needs an explicit timezone')
    if evidence_id in {item['id'] for item in state['evidence']}:
        raise ValueError('evidence ID already exists; choose a distinct revision ID')
    if not evidence_id.startswith('evidence.') or any(not (c.isalnum() or c in '._-') for c in evidence_id):
        raise ValueError('invalid evidence ID')
    requirements = state['requirements']
    def quantity(key, unit):
        value = requirements[key]
        if not isinstance(value, dict) or set(value) != {'value', 'unit'} or value['unit'] != unit:
            raise ValueError(f'{key} must be an explicit SI {unit} quantity')
        number = value['value']
        if type(number) not in (int, float) or not math.isfinite(number) or number <= 0:
            raise ValueError(f'{key} must be finite and positive')
        return number
    power = quantity('nominal_power', 'W')
    vin, vout = quantity('input_voltage', 'V'), quantity('output_voltage', 'V')
    references = requirements.get('evidence_refs', [])
    evidence = {item['id']: item for item in state['evidence']}
    if not references or any(ref not in evidence or evidence[ref]['review_status'] == 'rejected' for ref in references):
        raise ValueError('requirements need non-rejected input evidence')
    derived = {'nominal_output_current': {'value': power / vout, 'unit': 'A'},
               'voltage_ratio_out_in': {'value': vout / vin, 'unit': '1'},
               'evidence_refs': [evidence_id]}
    # Floating-point division can overflow even when operands are finite.
    if any(not math.isfinite(derived[key]['value']) for key in ('nominal_output_current', 'voltage_ratio_out_in')):
        raise ValueError('derived value overflow')
    result = copy.deepcopy(state)
    if 'aipe.design-agent' in result.get('extensions', {}):
        raise ValueError('existing design-agent results need an explicit review/revision; refusing to overwrite')
    result.setdefault('extensions', {})['aipe.design-agent'] = {
        'operating_point_analysis': derived, 'review_status': 'unreviewed',
        'limitations': ['P/V is nominal DC output current from requested ratings, not measured current.',
                        'Voltage ratio does not select transformer turns ratio, components, control, losses or efficiency.']}
    result['evidence'].append({
        'id': evidence_id, 'kind': 'analytical',
        'description': 'Nominal output current P_out/V_out and requested V_out/V_in ratio.',
        'source': {'type': 'repository', 'reference': 'https://github.com/FulongLi/AIPE-Design-Agent', 'locator': 'pea/adapters/__init__.py'},
        'provenance': {'created_at': created_at, 'activity': 'Compute two algebraic quantities from task-specified SI requirements.',
                       'tool': {'id': 'aipe.design-agent.operating-point-analysis', 'version': '0.1.0'},
                       'agent': {'id': 'aipe.design-agent', 'version': '0.1.0'}, 'inputs': list(references)},
        'artifacts': [], 'review_status': 'unreviewed'})
    return result
