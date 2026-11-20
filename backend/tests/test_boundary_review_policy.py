"""Minor boundary typography cannot veto a reviewed, semantically valid graph."""
import base64
import json
from unittest.mock import patch

import pytest

from app.diagram.narrative import review
from app.diagram.reliability import semantic_acceptance, retry_issues, retain_with_warning
from app.diagram.service import DiagramSpec, Edge, Node


@pytest.mark.parametrize('rule,description,advisory', [
    ('connector-heading-overlap', 'Wire crosses the Availability Zone and Private subnet headings.', True),
    ('boundary-label-overlap', 'AWS Account heading touches a Region boundary line.', True),
    ('connector-heading-overlap', 'Wire obscures an unreadable EC2 service caption.', False),
    ('detached-endpoint', 'Arrow is disconnected from the EC2 icon.', False),
    ('wrong-direction', 'Arrow reverses the actual application operation.', False),
])
def test_only_minor_boundary_text_findings_become_visible_advisories(rule, description, advisory):
    spec = DiagramSpec('Review', (Node('a', 'App', 'service', 0), Node('b', 'DB', 'service', 1)),
        (Edge('a', 'b'),), architecture_plan={})
    finding = {'stage': 'layout', 'rule_id': rule, 'severity': 'important', 'node_ids': ['a'],
        'edge_ids': ['e0'], 'step_ids': [], 'description': description,
        'evidence': description, 'repair_instruction': 'Adjust the presentation.'}
    asset = {'spec': spec.as_dict(), 'image_base64': base64.b64encode(b'image').decode(),
        'layout_engine': 'deployment_drawio', 'rendered_membership': {'a': [], 'b': []}}
    with patch('app.agents.architecture_reviewer_agent._call', return_value=json.dumps({'issues': [finding]})), \
         patch('app.agents.architecture_reviewer_agent.image_for_review', side_effect=lambda b: b), \
         patch('app.agents.architecture_reviewer_agent._audit'), \
         patch('app.diagram.deployment.projection', return_value=(spec, {})):
        checked = review(None, asset, spec, {})
    assert checked['vision_review']['image_reviewed']
    assert semantic_acceptance(checked) is advisory
    assert bool(retry_issues(checked)) is not advisory
    retained = retain_with_warning(checked)
    if advisory:
        assert checked['vision_review']['advisories'][0]['description'] == description
        assert retained['layout_advisories'] == [description]
        assert retained.get('status') != 'review_required'
    else:
        assert retained['status'] == 'review_required'
