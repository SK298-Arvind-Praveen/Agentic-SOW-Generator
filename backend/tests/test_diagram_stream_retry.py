import pytest
from urllib3.exceptions import ProtocolError
from app.diagram.reliability import structured_retry


@pytest.mark.parametrize('code',['serviceUnavailableException','ServiceUnavailableException',
    'internalServerException','modelStreamErrorException','throttlingException'])
def test_stream_event_errors_receive_one_retry(code,monkeypatch):
    from botocore.exceptions import ClientError
    monkeypatch.setattr('app.diagram.reliability.time.sleep',lambda _:None)
    calls = []
    def call(prompt):
        calls.append(prompt)
        if len(calls)==1:
            raise ClientError({'Error':{'Code':code,'Message':'Temporary failure'}},'ConverseStream')
        return '{"complete":true}'
    assert structured_retry(call,'Plan',lambda value:value,attempts=2)['complete']
    assert len(calls)==2


def test_permission_failure_is_not_retried(monkeypatch):
    from botocore.exceptions import ClientError
    calls = []
    def call(prompt):
        calls.append(prompt)
        raise ClientError({'Error':{'Code':'AccessDeniedException','Message':'Denied'}},'ConverseStream')
    with pytest.raises(ClientError):
        structured_retry(call,'Plan',lambda value:value,attempts=2)
    assert len(calls)==1


def test_premature_stream_retries_once_without_accepting_partial_text(monkeypatch):
    monkeypatch.setattr('app.diagram.reliability.time.sleep',lambda _:None)
    calls = []
    def call(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise ProtocolError('Response ended prematurely')
        return '{"complete":true}'
    assert structured_retry(call,'Plan',lambda value:value,attempts=2) == {'complete':True}
    assert len(calls) == 2


def test_premature_stream_exhaustion_is_bounded(monkeypatch):
    monkeypatch.setattr('app.diagram.reliability.time.sleep',lambda _:None)
    calls = []
    def call(prompt):
        calls.append(prompt)
        raise ProtocolError('Response ended prematurely')
    with pytest.raises(ValueError,match='ended prematurely'):
        structured_retry(call,'Plan',lambda value:value,attempts=2)
    assert len(calls) == 2


def test_corrective_prompt_preserves_the_complete_rejected_plan():
    import json
    calls = []
    def call(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps({'long_plan':'x'*25000, 'last_component':'keep_this_tail'})
        assert 'keep_this_tail' in prompt
        return '{"accepted":true}'
    def validate(value):
        if not value.get('accepted'):
            raise ValueError('Correct the final component')
        return value
    assert structured_retry(call,'Plan',validate,attempts=2) == {'accepted':True}
