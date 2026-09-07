"""Consistent ChatKit presentation; card actions never execute model work."""
import base64,struct,uuid
from pathlib import Path
from datetime import datetime,timezone
from chatkit.types import WidgetItem
from chatkit.widgets import Card,Row,Col,Text,Caption,Icon,Button,Spacer
from chatkit.widgets import Image

def action(label,kind,run_id,name=None,primary=False):
    payload={'run_id':run_id}
    if name is not None:payload['name']=name
    return Button(label=label,size='sm',block=False,style='primary' if primary else 'secondary',variant='soft' if primary else 'ghost',
        iconEnd='chevron-right' if primary else None,onClickAction={'type':kind,'handler':'client','payload':payload})

def header(title,subtitle,icon):
    return Row(align='center',gap=3,children=[Icon(name=icon,size='lg',color='secondary'),
        Col(gap=1,flex=1,children=[Text(value=title,weight='semibold',size='sm',maxLines=2),Caption(value=subtitle,color='secondary')])])

def app_card(run):
    return Card(theme='dark',background='surface-secondary',size='lg',padding=4,children=[
        header(run.get('title') or 'Your app is ready','Interactive app · opens beside this chat','desktop'),
        Row(margin={'top':3},align='center',children=[Caption(value='Saved project',color='secondary'),Spacer(),action('Open app','open_app',run['id'],primary=True)])])

def artifact_card(run,artifact,root):
    name=artifact['name'];suffix=Path(name).suffix.lower();path=root/'artifacts'/run['id']/name
    size=path.stat().st_size if path.is_file() else 0
    size_label=f'{size/1_000_000:.1f} MB' if size>=1_000_000 else f'{size/1000:.1f} KB' if size>=1000 else f'{size} B'
    kind,icon=('Image','square-image') if suffix in ('.png','.jpg','.jpeg','.webp','.svg') else ('Interactive HTML','globe') if suffix=='.html' else ('Data file','analytics') if suffix in ('.csv','.parquet','.xlsx','.json') else ('Source code','square-code') if suffix in ('.py','.js','.ts','.rs','.go','.cs','.cpp','.c','.jl','.sh') else ('File','document')
    paired=next((a for a in run.get('artifacts',[]) if a['name']==name[:-4]+'.html'),None) if suffix=='.png' else None
    children=[header(name,f'{"Interactive chart" if paired else kind} · {size_label}',icon)]
    if artifact.get('inline_png') or artifact.get('media_token'):
        raw=path.read_bytes()
        if 24<=len(raw)<=8_000_000 and raw.startswith(b'\x89PNG\r\n\x1a\n'):
            width,height=struct.unpack('>II',raw[16:24])
            if 0<width<=8192 and 0<height<=8192:
                children.append(Image(src='data:image/png;base64,'+base64.b64encode(raw).decode(),alt=name,width='100%',aspectRatio=width/height,fit='contain',radius='md',margin={'top':3}))
    buttons=[]
    if paired:buttons.append(action('Explore chart','open_artifact',run['id'],paired['name'],True))
    buttons.append(action('View image' if suffix=='.png' else 'Preview','open_artifact',run['id'],name,not paired))
    buttons.append(action('Download','download_artifact',run['id'],name))
    children.append(Row(gap=2,wrap='wrap',margin={'top':3},children=buttons))
    return Card(children=children,theme='dark',background='surface-secondary',padding=4,size='full' if len(children)>2 else 'lg')

def item(thread,card):
    return WidgetItem(id='widget_'+uuid.uuid4().hex,thread_id=thread.id,created_at=datetime.now(timezone.utc),widget=card)
