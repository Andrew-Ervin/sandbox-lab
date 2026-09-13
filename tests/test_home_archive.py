import io
import os
import tarfile
import pytest
from sandbox import home_archive


def test_home_transfer_spans_bounded_files_and_preserves_content(tmp_path,monkeypatch):
    monkeypatch.setattr(home_archive,'CHUNK_BYTES',1024)
    home=tmp_path/'home';home.mkdir()
    expected=os.urandom(16000);(home/'code.bin').write_bytes(expected)
    (home/'internal').symlink_to(home/'code.bin')
    outside=tmp_path/'private';outside.write_text('not copied')
    (home/'external').symlink_to(outside)
    parts=tmp_path/'parts';metadata=home_archive.pack(home,parts)
    files=sorted(parts.iterdir())
    assert metadata['parts']==len(files)>1
    assert max(p.stat().st_size for p in files)<=1024
    assert metadata['bytes']==sum(p.stat().st_size for p in files)
    assert metadata['skipped_external_links']==1
    with tarfile.open(fileobj=io.BytesIO(b''.join(p.read_bytes() for p in files))) as archive:
        assert archive.extractfile('code.bin').read()==expected
        assert 'external' not in archive.getnames()
        assert archive.getmember('internal').linkname=='code.bin'


def test_compressed_limit_still_applies_across_segments(tmp_path,monkeypatch):
    monkeypatch.setattr(home_archive,'CHUNK_BYTES',100)
    monkeypatch.setattr(home_archive,'MAX_ARCHIVE_BYTES',150)
    writer=home_archive.Parts(tmp_path/'parts')
    writer.write(b'x'*120)
    with pytest.raises(ValueError,match='safe migration limit'):writer.write(b'x'*31)
    writer.close()
    assert sum(p.stat().st_size for p in (tmp_path/'parts').iterdir())==120
