from app.pricing.volumes import selected_volumes, append_volume_assumptions
from app.pricing.renderer import render_aws_pricing_section


def test_same_estimated_volumes_in_pricing_and_assumptions():
    result={'status':'priced','monthly_cost':10,'volume_metrics':[
        {'metric':'Average monthly conversations','value':'10000','status':'Approximated'},
        {'metric':'Operating hours','value':'160 per month','status':'Source-backed'},
        {'metric':'Custom vocabulary defect terms','value':'50','status':'Source-backed'}]}
    text=render_aws_pricing_section(result)
    assert '| Workload volume | Value |' in text
    assert '| Average monthly conversations | 10000 (Approx.) |' in text
    assert '| Operating hours | 160 per month |' in text
    assert 'defect terms' not in text
    assumptions=append_volume_assumptions('Existing assumption.',result)
    assert '10000 (Approx.)' in assumptions and 'Operating hours' not in assumptions
    assert append_volume_assumptions(assumptions,result)==assumptions


def test_volume_list_is_bounded_and_missing_provenance_is_estimated():
    result={'volume_metrics':[{'metric':f'Monthly requests {i}','value':100+i} for i in range(10)]}
    assert len(selected_volumes(result))==5
    assert all(row[2] for row in selected_volumes(result))
