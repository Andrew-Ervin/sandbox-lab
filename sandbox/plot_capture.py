"""Capture Plotly show()/write_html() as portable HTML and inline PNG outputs."""
import runpy
from pathlib import Path
from plotly.basedatatypes import BaseFigure

original_html=BaseFigure.write_html
counter=0
def capture(fig, *args, **kwargs):
    global counter
    counter+=1
    target=Path('/workspace/artifacts')/f'figure-{counter}'
    # Keep a complete interactive version even if static rendering fails.
    original_html(fig,str(target)+'.html',include_plotlyjs=True)
    specs=Path('/workspace/plots'); specs.mkdir(exist_ok=True)
    # The pod supervisor renders this data after the user process exits.
    fig.write_json(specs/f'figure-{counter}.json')
def write_html(fig,*args,**kwargs):
    result=original_html(fig,*args,**kwargs)
    capture(fig)
    return result
BaseFigure.write_html=write_html
BaseFigure.show=capture
runpy.run_path('/workspace/main.py',run_name='__main__')
