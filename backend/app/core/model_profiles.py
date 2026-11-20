"""Named Bedrock selections shared by configuration and invocation adapters."""

_PREFIX = 'arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/'

MODEL_PROFILES = {
    'sonnet-5': {'label': 'Claude Sonnet 5', 'id': _PREFIX + '20kstbja9ona', 'family': 'claude'},
    'haiku': {'label': 'Claude Haiku 4.5', 'id': _PREFIX + 'oj2y908xxkkf', 'family': 'claude'},
    'sonnet-5.5': {'label': 'Claude Sonnet 5.5', 'id': _PREFIX + 'hlc2w29214np', 'family': 'claude'},
    'opus-5.5': {'label': 'Claude Opus 5.5', 'id': _PREFIX + 'lwjwoyltuicz', 'family': 'claude-opus'},
    'gpt-6-astra': {'label': 'GPT-6 Astra', 'id': _PREFIX + 'o8dwriwugus2', 'family': 'openai'},
}


def resolve_model(value):
    """Accept a named selection or an existing Bedrock model/profile identifier."""
    value = str(value).strip()
    profile = MODEL_PROFILES.get(value.casefold())
    return profile['id'] if profile else value


def model_family(value):
    identifier = resolve_model(value).casefold()
    for profile in MODEL_PROFILES.values():
        if identifier == profile['id'].casefold():
            return profile['family']
    return 'openai' if 'openai.' in identifier else ''


def available_models():
    return [{'key': key, **profile} for key, profile in MODEL_PROFILES.items()]
