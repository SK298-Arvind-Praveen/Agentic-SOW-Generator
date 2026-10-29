"""UI removal must not require a hidden choice or bypass ownership checks."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def resolve_record_unit(identity, requested):
    tree = ast.parse((ROOT / 'backend/app/core/server.py').read_text(encoding='utf-8-sig'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == '_business_unit_for_new_record')
    namespace = {'current_identity': lambda: identity, '_requested_business_unit': requested}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<ownership>', 'exec'), namespace)
    return namespace['_business_unit_for_new_record']()


@pytest.mark.parametrize('primary', [None, 'GenAI', 'Cloud'])
def test_no_selection_uses_existing_assignment(primary):
    assert resolve_record_unit(SimpleNamespace(business_unit=primary), lambda: None) == (primary, None)


def test_explicit_validated_assignment_is_preserved():
    assert resolve_record_unit(SimpleNamespace(business_unit='GenAI'), lambda: 'Cloud') == ('Cloud', None)


def test_forbidden_explicit_assignment_still_fails():
    def denied():
        raise ValueError('Forbidden business unit')
    with pytest.raises(ValueError, match='Forbidden'):
        resolve_record_unit(SimpleNamespace(business_unit='GenAI'), denied)


@pytest.mark.parametrize('page', ['SOWGenerator', 'Dashboard', 'Accounts', 'SOWRecords', 'SOWTracker'])
def test_operational_pages_do_not_show_business_unit_controls(page):
    source = (ROOT / f'frontend/src/components/{page}.tsx').read_text(encoding='utf-8-sig')
    assert 'Business Unit' not in source
    assert 'Select business unit' not in source
    if page == 'SOWGenerator':
        assert 'if (!formData.businessUnit)' not in source
