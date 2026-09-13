"""Validate complete model output before dispatching any of its tool calls."""
import json


def response_problem(choice):
    if choice.get('finish_reason') == 'length':
        return 'The model reached its response limit before finishing.'
    message = choice.get('message') or {}
    calls = message.get('tool_calls') or []
    for call in calls:
        try:
            function = call['function']
            if not isinstance(function['name'], str) or not function['name']:
                raise ValueError('Missing tool name')
            arguments = json.loads(function['arguments'])
            if not isinstance(arguments, dict):
                raise ValueError('Tool arguments must be an object')
        except (KeyError, TypeError, ValueError):
            return 'The model returned an incomplete or invalid tool request.'
    if not calls and not (message.get('content') or '').strip():
        return 'The model returned no answer.'
    return None
