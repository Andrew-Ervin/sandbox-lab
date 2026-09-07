"""Bounded, provider-supplied activity for native Coder runs; no host environment."""
import json
from .limits import value
from .markdown import fenced


def snapshot(messages):
    messages=messages[-value('NATIVE_TELEMETRY_MAX_MESSAGES'):]
    completed={p.get('tool_call_id'):p for m in messages for p in (m.get('content') or []) if p.get('type')=='tool-result'}
    details=[];usage={};calls=0
    for message in messages:
        for key in ('input_tokens','output_tokens','reasoning_tokens','cache_read_tokens'):
            count=(message.get('usage') or {}).get(key)
            if type(count) is int and count>=0:usage[key]=usage.get(key,0)+count
        for part in message.get('content') or []:
            if message.get('role')!='assistant':continue
            if part.get('type')=='reasoning' and isinstance(part.get('text'),str) and part['text'].strip():
                details.append('### Reasoning · supplied by the model\n'+part['text'][:6000])
            if part.get('type')=='tool-call':
                calls+=1;result=completed.get(part.get('tool_call_id'))
                state='failed' if result and result.get('is_error') else 'completed' if result else 'running'
                name=str(part.get('tool_name') or part.get('name') or 'Tool')[:80]
                args=part.get('args') or part.get('input') or {}
                rendered=args if isinstance(args,str) else json.dumps(args,ensure_ascii=False,indent=2)
                details.append('### '+name+' · '+state+'\n'+fenced(rendered[:2500],'json'))
    budget=value('NATIVE_TELEMETRY_MAX_CHARS');selected=[];used=0
    # Retain complete recent blocks. Never split Markdown fences mid-block.
    for block in reversed(details):
        cost=len(block)+(2 if selected else 0)
        if used+cost>budget:break
        selected.append(block);used+=cost
    return {'details':'\n\n'.join(reversed(selected)), 'tool_calls':calls,'usage':usage,'truncated':len(selected)<len(details)}
