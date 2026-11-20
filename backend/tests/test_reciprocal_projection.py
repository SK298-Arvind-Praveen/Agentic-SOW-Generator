from app.diagram.service import Edge
from app.diagram.projection import merge_reciprocal_links


def test_reciprocal_overview_wires_share_one_traceable_two_way_connector():
    forward={'edge':Edge('loader','database'),'paths':[[0],[2]]}
    reverse={'edge':Edge('database','loader'),'paths':[[1]]}
    other={'edge':Edge('loader','store'),'paths':[[3]]}
    links=merge_reciprocal_links([forward,reverse,other])
    assert len(links)==2
    assert links[0]['both'] is True
    assert links[0]['paths']==[[0],[2],[1]]
    assert links[1]==other
    assert forward=={'edge':Edge('loader','database'),'paths':[[0],[2]]}


def test_one_way_or_parallel_operations_do_not_invent_a_reverse_arrow():
    links=[{'edge':Edge('app','db'),'paths':[[0]]},{'edge':Edge('app','db'),'paths':[[1]]}]
    assert merge_reciprocal_links(links)==links
