"""Shared presentation for human approval requests; this module cannot approve tools."""
from .chat_cards import header
from chatkit.widgets import Card, Col, Row, Text, Caption, Button


def approval_card(*, title, fields, body, thread_id, item_id, decision=None, action=None):
    """Show a readable excerpt and a separate full-payload viewer; decisions stay native."""
    status = {'text': decision or 'Your approval is needed', 'icon': 'check' if decision else 'info'}
    children = [header(title, 'Review the request before continuing', 'document')]
    children.append(Col(gap=2, margin={'top':3}, children=[
        Row(gap=3, children=[Caption(value=label, color='secondary'), Text(value=value, size='sm')])
        for label, value in fields
    ]))
    excerpt = body[:900]
    if len(body)>len(excerpt):excerpt=excerpt.rsplit(' ',1)[0]+'…'
    children.append(Col(gap=2, margin={'top':3}, children=[Text(value=p, size='sm') for p in excerpt.split('\n\n') if p]))
    children.append(Row(gap=2, margin={'top':3}, children=[
        Button(label='View full request', size='sm', block=False, variant='outline',
               onClickAction={'type':'open_approval_payload','handler':'client','payload':{'thread_id':thread_id,'item_id':item_id}}),
        Caption(value=f'{len(body.split())} words' if body else 'Exact JSON payload', color='secondary'),
    ]))
    confirm=cancel=None
    if not decision and action:
        confirm={'label':'Approve and continue','action':{**action,'payload':{**action['payload'],'decision':'approve'}}}
        cancel={'label':'Reject','action':{**action,'payload':{**action['payload'],'decision':'reject'}}}
    return Card(theme='dark',background='surface-secondary',size='full',padding=4,status=status,
                collapsed=bool(decision),children=children,confirm=confirm,cancel=cancel)
