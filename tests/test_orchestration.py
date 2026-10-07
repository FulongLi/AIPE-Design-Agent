import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pea.adapters import analyse_operating_point
from pea.orchestration import select_capability
from pea.registry import load_registry
from pea.state import load_json, validate_state

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def state():
    return load_json(ROOT / 'tests/fixtures/dab-10kw.json')


def candidate(ident, tool, licence='open_source', validation='tested'):
    return {'id': ident, 'repository': f'https://github.com/Example/{tool}', 'status': 'active',
            'capabilities': ['switching-circuit-simulation'],
            'validation': {'status': validation, 'limitations': ['Model needs review.']},
            'tools': [{'id': tool, 'capabilities': ['switching-circuit-simulation'], 'licence_class': licence,
                       'platforms': ['linux', 'windows'], 'limitations': ['No physical certification.']}]}


def assessment(ident, tool, score=1.0, fidelities=None):
    return {'capability_id': ident, 'tool_id': tool, 'capability': 'switching-circuit-simulation',
            'suitability': score, 'fidelities': fidelities or ['switching-waveform'], 'rationale': 'Test assessment for explicit model fidelity.'}


def select(items, assessments, **kwargs):
    return select_capability({'capabilities': items}, 'switching-circuit-simulation', assessments,
                             kwargs.pop('installed', ['open', 'commercial']), kwargs.pop('platform', 'linux'),
                             fidelity='switching-waveform', **kwargs)


def test_open_preferred_only_when_technically_equivalent():
    items = [candidate('aipe.open', 'open'), candidate('aipe.commercial', 'commercial', 'commercial')]
    a = [assessment('aipe.open', 'open'), assessment('aipe.commercial', 'commercial')]
    assert select(items, a)['selected']['tool_id'] == 'open'
    a[0]['suitability'] = 0.5
    assert select(items, a)['selected']['tool_id'] == 'commercial'


def test_user_commercial_preference_kept_among_equivalent_paths():
    items = [candidate('aipe.open', 'open'), candidate('aipe.commercial', 'commercial', 'commercial')]
    a = [assessment('aipe.open', 'open'), assessment('aipe.commercial', 'commercial')]
    assert select(items, a, preferred=['commercial'])['selected']['tool_id'] == 'commercial'


def test_wrong_fidelity_cannot_win_through_accessibility():
    items = [candidate('aipe.open', 'open'), candidate('aipe.commercial', 'commercial', 'commercial')]
    a = [assessment('aipe.open', 'open', fidelities=['averaged-model']), assessment('aipe.commercial', 'commercial')]
    result = select(items, a)
    assert result['selected']['tool_id'] == 'commercial'
    assert 'fidelity' in result['rejected'][0]['reasons'][0]


@pytest.mark.parametrize('kwargs,reason', [({'installed': []}, 'available'), ({'platform': 'macos'}, 'platform'), ({'minimum_validation': 'measured'}, 'validation')])
def test_availability_platform_validation_gates(kwargs, reason):
    result = select([candidate('aipe.open', 'open')], [assessment('aipe.open', 'open')], **kwargs)
    assert result['selected'] is None
    assert any(reason in r for r in result['rejected'][0]['reasons'])


def test_unassessed_path_and_wrong_capability_cannot_execute():
    item = candidate('aipe.open', 'open')
    result = select([item], [])
    assert result['selected'] is None and result['execution'] == 'not_run'
    item['tools'][0]['capabilities'] = ['thermal-fea']
    assert select([item], [assessment('aipe.open', 'open')])['selected'] is None


def test_selection_is_deterministic_and_does_not_mutate_inputs():
    items = [candidate('aipe.open', 'open'), candidate('aipe.commercial', 'commercial', 'commercial')]
    a = [assessment('aipe.open', 'open'), assessment('aipe.commercial', 'commercial')]
    before = copy.deepcopy(items)
    assert select(items, a) == select(list(reversed(items)), list(reversed(a)))
    assert items == before


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -1, 2, True, '1'])
def test_invalid_suitability_rejected(score):
    with pytest.raises(ValueError):
        select([candidate('aipe.open', 'open')], [assessment('aipe.open', 'open', score)])


def test_local_adapter_preserves_state_and_labels_analytical_evidence(state):
    original = copy.deepcopy(state)
    result = analyse_operating_point(state, '2026-10-07T00:00:00Z')
    analysis = result['extensions']['aipe.design-agent']['operating_point_analysis']
    assert analysis['nominal_output_current'] == {'value': 25.0, 'unit': 'A'}
    assert analysis['voltage_ratio_out_in'] == {'value': 0.5, 'unit': '1'}
    assert result['evidence'][-1]['kind'] == 'analytical'
    assert result['evidence'][-1]['review_status'] == 'unreviewed'
    assert result['evidence'][-1]['provenance']['inputs'] == ['evidence.design-brief']
    for key in ['converter', 'semiconductors', 'magnetics', 'thermal', 'simulation', 'validation']:
        assert result[key] == original[key]
    assert state == original
    assert result == analyse_operating_point(state, '2026-10-07T00:00:00Z')


@pytest.mark.parametrize('value,unit', [(0, 'V'), (-1, 'V'), (400, 'mV'), (float('inf'), 'V'), (True, 'V')])
def test_adapter_rejects_unsafe_or_ambiguous_quantity(state, value, unit):
    state['requirements']['output_voltage'] = {'value': value, 'unit': unit}
    with pytest.raises(ValueError):
        analyse_operating_point(state, '2026-10-07T00:00:00Z')


def test_adapter_rejects_rejected_evidence_and_overwrite(state):
    result = analyse_operating_point(state, '2026-10-07T00:00:00Z')
    with pytest.raises(ValueError, match='already exists'):
        analyse_operating_point(result, '2026-10-07T00:00:00Z')
    with pytest.raises(ValueError, match='overwrite'):
        analyse_operating_point(result, '2026-10-07T00:00:00Z', 'evidence.second')
    state['evidence'][0]['review_status'] = 'rejected'
    with pytest.raises(ValueError, match='evidence'):
        analyse_operating_point(state, '2026-10-07T00:00:00Z')


def test_reject_duplicate_json_and_registry_envelope(tmp_path):
    source = tmp_path / 'input.json'
    source.write_text('{"id":1,"id":2}')
    with pytest.raises(ValueError, match='duplicate'):
        load_json(source)
    source.write_text('{"schema_version":"0.2.0","capabilities":[]}')
    with pytest.raises(ValueError, match='envelope'):
        load_registry(source, tmp_path / 'unused-schema.json')


def test_cli_help_needs_no_llm_or_commercial_stack():
    result = subprocess.run([sys.executable, '-m', 'pea.orchestration', '--help'], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0 and '--execute-local' in result.stdout


def test_complete_state_contract_against_local_core_when_available(state):
    core = ROOT.parent / 'AIPE-Core'
    if not (core / 'schemas/engineering-state.schema.json').is_file():
        pytest.skip('Cross-repository integration requires the versioned Core checkout; standalone adapter tests run above.')
    validate_state(state, core)
    validate_state(analyse_operating_point(state, '2026-10-07T00:00:00Z'), core)
