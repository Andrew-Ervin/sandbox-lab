"""Assemble OpenRouter SSE responses without executing partial tool arguments."""
import json
import httpx


class Accumulator:
    def __init__(self, activity):
        self.activity = activity
        self.message = {'role': 'assistant', 'content': ''}
        self.calls = {}
        self.details = {}
        self.finish = None

    def add(self, chunk):
        if chunk.get('error'):
            raise RuntimeError('The model stream failed before completing; no pending tool was executed.')
        for choice in chunk.get('choices') or []:
            if choice.get('index', 0) != 0:
                continue
            self.finish = choice.get('finish_reason') or self.finish
            delta = choice.get('delta') or {}
            if delta.get('content'):
                self.message['content'] += delta['content']
                self.activity['phase'] = 'Writing response'
                self.activity['answer_chars'] = len(self.message['content'])
                self.activity['answer'] = self.message['content']
            if delta.get('annotations'):
                self.message.setdefault('annotations', []).extend(delta['annotations'])
            for detail in delta.get('reasoning_details') or []:
                key = (detail.get('index', 0), detail.get('type', ''))
                target = self.details.setdefault(key, {})
                for k, v in detail.items():
                    if k in ('text', 'summary', 'data') and isinstance(v, str):
                        target[k] = target.get(k, '') + v
                    elif v is not None:
                        target[k] = v
            if delta.get('reasoning'):
                self.message['reasoning'] = self.message.get('reasoning', '') + delta['reasoning']
            readable = '\n\n'.join(d.get('summary') or d.get('text') or '' for d in self.details.values())
            readable = readable.strip() or self.message.get('reasoning', '')
            if readable:
                self.activity['reasoning'] = readable[-16000:]
                if not self.calls and not self.message['content']:
                    self.activity['phase'] = 'Thinking'
            for call in delta.get('tool_calls') or []:
                target = self.calls.setdefault(call['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if call.get('id'): target['id'] = call['id']
                for k in ('name', 'arguments'):
                    target['function'][k] += (call.get('function') or {}).get(k) or ''
                name = target['function']['name']
                self.activity['phase'] = 'Writing Python code' if name == 'run_python' else 'Preparing tool request'
                self.activity['tool'] = name
                self.activity['argument_chars'] = sum(len(c['function']['arguments']) for c in self.calls.values())
        if chunk.get('usage'):
            self.activity['usage'] = chunk['usage']

    def result(self):
        if self.calls: self.message['tool_calls'] = list(self.calls.values())
        if self.details: self.message['reasoning_details'] = list(self.details.values())
        return {'choices': [{'message': self.message, 'finish_reason': self.finish}]}


async def stream_response(client, url, body, headers, activity):
    activity.clear()
    activity['phase'] = 'Waiting for model'
    state = Accumulator(activity)
    async with client.stream('POST', url, json={**body, 'stream': True}, headers=headers) as response:
        if response.status_code >= 400 or 'text/event-stream' not in response.headers.get('content-type', ''):
            await response.aread()
            return response
        async for line in response.aiter_lines():
            if not line.startswith('data:'): continue
            data = line[5:].strip()
            if data == '[DONE]': break
            if data: state.add(json.loads(data))
    if state.finish is None:
        raise httpx.RemoteProtocolError('Model stream ended without a finish marker')
    return httpx.Response(200, json=state.result())
