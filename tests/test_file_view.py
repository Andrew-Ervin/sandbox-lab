from backend.file_view import render

def test_csv_and_code_previews_escape_markup_instead_of_executing_it():
    csv=render(b'name,value\n<script>alert(1)</script>,42','data.csv').decode()
    assert '<table>' in csv and '&lt;script&gt;' in csv and '<script>alert' not in csv
    code=render(b'print("hello")\n</script><img src=https://evil.test>','main.py').decode()
    assert '<ol class="source">' in code and '&lt;img' in code and '<img src=' not in code

def test_large_csv_source_and_binary_have_bounded_explanatory_views():
    table=render(b'x,y\n'+b'1,2\n'*10000,'large.csv').decode()
    assert table.count('<tr>')==501 and 'Preview shortened' in table
    source=render(b'line\n'*100000,'large.py').decode()
    assert source.count('<li>')==3000 and len(source)<150000
    assert b'binary file' in render(b'\x00\xff','model.bin')
