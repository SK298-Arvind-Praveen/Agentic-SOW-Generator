from dataclasses import replace
from app.diagram.service import Node, Edge
from app.diagram.narrative import geometry
from tests.test_narrative_architecture import architecture


def test_downstream_external_chain_stays_on_output_rail(architecture):
    spec, plan, _ = architecture
    spec = replace(spec, nodes=spec.nodes + (Node('erp','ERP','external',0,scope='external'),),
                   edges=spec.edges + (Edge('external','erp','Post record'),))
    positions, boxes, _, _, _ = geometry(spec, plan)
    cloud_bottom = boxes['cloud'][1] + boxes['cloud'][3]
    assert positions['external'][1] == positions['erp'][1] > cloud_bottom
    assert positions['user'][1] < boxes['cloud'][1]
