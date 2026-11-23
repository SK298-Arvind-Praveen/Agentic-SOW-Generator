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
    assert 'Average monthly conversations are estimated at 10000.' in assumptions
    assert 'Operating hours' not in assumptions
    assert 'Pricing assumes' not in assumptions and '(Approx.)' not in assumptions
    assert append_volume_assumptions(assumptions,result)==assumptions


def test_volume_list_is_bounded_and_missing_provenance_is_estimated():
    result={'volume_metrics':[{'metric':f'Monthly requests {i}','value':100+i} for i in range(10)]}
    assert len(selected_volumes(result))==5
    assert all(row[2] for row in selected_volumes(result))


def test_plain_english_volume_assumptions_and_legacy_upgrade():
    from app.pricing.volumes import volume_assumption
    assert volume_assumption('Monthly active users', '100 MAU') == 'There are approximately 100 monthly active users.'
    assert volume_assumption('Base monthly streaming audio', '300 × 3 × 10 s × 26 days ≈ 3,900 min/month') == 'Base monthly streaming audio is estimated at 3,900 min/month.'
    assert volume_assumption('Hours per day at this rate', '16 hours/day (two shifts)') == 'Operations run for approximately 16 hours per day (two shifts).'
    assert volume_assumption('Usage-hours assumption', 'Monthly operation, not total POC duration') == 'Usage hours represent a typical month of operation, rather than the total POC duration.'
    result = {'volume_metrics': [{'metric': 'Monthly active users', 'value': '100 MAU', 'status': 'estimated'}]}
    text = append_volume_assumptions('- Pricing assumes Monthly active users: 100 MAU (Approx.).', result)
    assert text == '- There are approximately 100 monthly active users.'
    assert append_volume_assumptions(text, result) == text
