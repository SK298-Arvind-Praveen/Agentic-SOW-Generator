def test_diagram_profile_is_isolated_from_other_tasks(monkeypatch):
    from app.core.config import Config
    from app.core.bedrock_llm import model_for_task
    monkeypatch.delenv('BEDROCK_DIAGRAM_MODEL_ID',raising=False)
    monkeypatch.delenv('BEDROCK_DIAGRAM_REVIEW_MODEL_ID',raising=False)
    for key,value in [('BEDROCK_ANALYSIS_MODEL_ID','analysis'),('BEDROCK_WRITER_MODEL_ID','writer'),
                      ('BEDROCK_FAST_MODEL_ID','fast'),('BEDROCK_EDITOR_MODEL_ID','editor'),
                      ('BEDROCK_FALLBACK_MODEL_ID','fallback')]:
        monkeypatch.setenv(key,value)
    config=Config()
    assert model_for_task(config,'diagram').endswith('/hlc2w29214np')
    assert config.DIAGRAM_REVIEW_MODEL_ID == config.DIAGRAM_MODEL_ID
    for task in ('analysis','writer','fast','editor','fallback'):
        assert model_for_task(config,task)==task
