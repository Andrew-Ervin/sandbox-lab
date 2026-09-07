"""Operator-owned routing, shared by chat, the workspace gateway and Coder setup."""
import os


def web_search_tool():
    """Only the operator enables server-side search; callers cannot choose a provider."""
    if os.getenv('LAB_ALLOW_WEB_SEARCH', 'true').lower() != 'true':
        return None
    return {'type': 'openrouter:web_search', 'parameters': {
        'engine': 'exa', 'max_results': int(os.getenv('WEB_SEARCH_MAX_RESULTS', '3')),
        'max_total_results': int(os.getenv('WEB_SEARCH_MAX_TOTAL_RESULTS', '6')),
        'max_uses': int(os.getenv('WEB_SEARCH_MAX_USES', '2')), 'search_context_size': 'low'}}


def require_zdr():
    raw = os.getenv('OPENROUTER_REQUIRE_ZDR', 'false').lower()
    if raw not in {'true', 'false'}:
        raise ValueError('OPENROUTER_REQUIRE_ZDR must be true or false')
    return raw == 'true'


def provider_policy(*, speech=False):
    collection = os.getenv('OPENROUTER_DATA_COLLECTION', 'deny')
    if collection not in {'deny', 'allow'}:
        raise ValueError('OPENROUTER_DATA_COLLECTION must be deny or allow')
    policy = {'zdr': require_zdr(), 'data_collection': collection}
    # OpenRouter transcription ignores provider selection. Its endpoint eligibility
    # is checked separately when ZDR is enabled; LLM routing does not apply to STT.
    if not speech:
        for field, default in [('order', 'amazon-bedrock,openai'), ('ignore', 'azure')]:
            values = [s.strip() for s in os.getenv('OPENROUTER_PROVIDER_' + field.upper(), default).split(',') if s.strip()]
            if values:
                policy[field] = values
        policy['allow_fallbacks'] = True
    return policy
