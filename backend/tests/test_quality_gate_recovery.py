from app.agents.poc_writer_agent import recover_missing_sections


def test_missing_assumptions_retried_once_without_changing_other_sections():
    output={'scope_of_work':'Approved scope','assumptions':''};calls=[]
    def repair(key):calls.append(key);return '- Test data is sanitized.'
    warnings=recover_missing_sections(output,['assumptions'],repair)
    assert calls==['assumptions']
    assert output['scope_of_work']=='Approved scope'
    assert output['assumptions']=='- Test data is sanitized.'
    assert warnings and 'regenerated' in warnings[0]


def test_failed_repair_preserves_preview_and_reports_missing_section():
    output={'scope_of_work':'Approved scope','assumptions':''};calls=[]
    def repair(key):calls.append(key);raise TimeoutError('model unavailable')
    warnings=recover_missing_sections(output,['assumptions'],repair)
    assert calls==['assumptions'] and output['scope_of_work']=='Approved scope'
    assert output['assumptions']=='' and 'remains empty' in warnings[0]


def test_blank_repair_is_warning_not_false_success():
    output={'assumptions':''}
    assert 'remains empty' in recover_missing_sections(output,['assumptions'],lambda key:' ')[0]
