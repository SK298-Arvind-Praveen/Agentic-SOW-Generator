from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.diagram.conceptual_safe import generate_optional


@pytest.mark.parametrize('succeeds',[True,False])
def test_retry_then_continue_without_discarding_content(monkeypatch,succeeds):
    client=Mock()
    monkeypatch.setattr('app.diagram.service.DiagramService',lambda config: SimpleNamespace(llm=object(),bedrock=client))
    generator=Mock(side_effect=[ValueError('booking -> data'), {'image_base64':'png'} if succeeds else RuntimeError('export failed')])
    monkeypatch.setattr('app.diagram.conceptual_drawio.generate',generator)
    asset=generate_optional(None,{},'source',{},['scope'])
    assert generator.call_count==2
    assert asset['following_sections']==['scope']
    assert asset['image_base64']==('png' if succeeds else '')
    assert 'booking -> data' in generator.call_args.kwargs['review_feedback']
    client.close.assert_called_once()


def test_client_setup_failure_is_nonfatal(monkeypatch):
    factory=Mock(side_effect=RuntimeError('client unavailable'))
    monkeypatch.setattr('app.diagram.service.DiagramService',factory)
    assert generate_optional(None,{},'',{},[])['status']=='unavailable'
    assert factory.call_count==2


def test_cancellation_is_not_swallowed_or_retried(monkeypatch):
    from app.preview.cancellation import GenerationCancelled
    client=Mock()
    monkeypatch.setattr('app.diagram.service.DiagramService',lambda config: SimpleNamespace(llm=None,bedrock=client))
    generate=Mock(side_effect=GenerationCancelled())
    monkeypatch.setattr('app.diagram.conceptual_drawio.generate',generate)
    with pytest.raises(GenerationCancelled):
        generate_optional(None,{},'',{},[])
    assert generate.call_count==1
    client.close.assert_called_once()
