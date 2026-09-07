"""Artifact imports must stay confined and bounded despite stale metadata/races."""
import base64
import os
from types import SimpleNamespace

import pytest
from backend import files


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(files, 'STATE', tmp_path)
    monkeypatch.setenv('ARTIFACT_MAX_FILE_BYTES', '8')
    monkeypatch.setenv('ARTIFACT_MAX_TOTAL_BYTES', '12')
    folder = tmp_path / 'artifacts' / 'run_test'
    folder.mkdir(parents=True)
    records = []

    def add(name, raw, reported_size=0):
        path = folder / name
        path.write_bytes(raw)
        records.append({'run_id': 'run_test', 'name': name, 'size': reported_size})
        return path

    return SimpleNamespace(add=add, folder=folder, records=records,
                           store=SimpleNamespace(files=lambda thread: records))


def test_actual_bytes_override_stale_catalog_sizes(catalog):
    catalog.add('a.txt', b'123456', reported_size=1000000)
    catalog.add('b.txt', b'123456', reported_size=0)
    result = files.inputs(catalog.store, 'chat')
    assert sum(len(base64.b64decode(f['data'])) for f in result) == 12
    (catalog.folder / 'b.txt').write_bytes(b'1234567')
    with pytest.raises(ValueError, match='total byte limit'):
        files.inputs(catalog.store, 'chat')


@pytest.mark.parametrize('target', ['file', 'run', 'artifacts'])
def test_symlink_swap_during_open_is_rejected(catalog, monkeypatch, target):
    path = catalog.add('a.txt', b'private')
    original_open = os.open
    trigger = {'file': 'a.txt', 'run': 'run_test', 'artifacts': 'artifacts'}[target]
    victim = {'file': path, 'run': catalog.folder, 'artifacts': catalog.folder.parent}[target]
    swapped = False

    def swap(name, flags, *args, **kwargs):
        nonlocal swapped
        if name == trigger and not swapped:
            swapped = True
            moved = victim.with_name(victim.name + '-moved')
            victim.rename(moved)
            victim.symlink_to(moved, target_is_directory=target != 'file')
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(files.os, 'open', swap)
    assert files.inputs(catalog.store, 'chat') == []
    assert swapped


def test_replacing_path_after_open_keeps_original_inode(catalog, monkeypatch):
    path = catalog.add('a.txt', b'original')
    original_read = os.read
    replaced = False

    def replace(fd, count):
        nonlocal replaced
        if not replaced:
            replaced = True
            path.unlink()
            path.write_bytes(b'changed')
        return original_read(fd, count)

    monkeypatch.setattr(files.os, 'read', replace)
    assert base64.b64decode(files.inputs(catalog.store, 'chat')[0]['data']) == b'original'


@pytest.mark.parametrize('prior_bytes', [0, 6])
def test_growth_after_fstat_cannot_bypass_byte_limits(catalog, monkeypatch, prior_bytes):
    if prior_bytes:
        catalog.add('a.txt', b'x' * prior_bytes)
    path = catalog.add('b.txt', b'x')
    original_fstat = os.fstat
    inode = path.stat().st_ino
    grown = False

    def grow(fd):
        nonlocal grown
        info = original_fstat(fd)
        if info.st_ino == inode and not grown:
            grown = True
            path.write_bytes(b'x' * 100)
        return info

    monkeypatch.setattr(files.os, 'fstat', grow)
    if prior_bytes:
        with pytest.raises(ValueError, match='total byte limit'):
            files.inputs(catalog.store, 'chat')
    else:
        assert files.inputs(catalog.store, 'chat') == []
    assert grown


def test_nonregular_missing_and_oversize_files_are_skipped(catalog):
    path = catalog.add('fifo', b'')
    path.unlink()
    os.mkfifo(path)
    path = catalog.add('directory', b'')
    path.unlink()
    path.mkdir()
    catalog.add('missing', b'').unlink()
    catalog.add('large', b'x' * 9)
    catalog.add('empty', b'')
    assert files.inputs(catalog.store, 'chat') == [{'name': 'empty', 'data': ''}]


@pytest.mark.parametrize('field,value', [('name', '../secret'), ('run_id', '../outside'), ('name', '/tmp/secret')])
def test_catalog_paths_cannot_escape_artifact_root(catalog, field, value):
    catalog.add('a.txt', b'normal')
    catalog.records[0][field] = value
    with pytest.raises(ValueError, match='Invalid conversation file path'):
        files.inputs(catalog.store, 'chat')


def test_implicit_selection_also_enforces_file_count(catalog, monkeypatch):
    monkeypatch.setenv('ARTIFACT_MAX_FILES', '1')
    catalog.add('a.txt', b'a')
    catalog.add('b.txt', b'b')
    with pytest.raises(ValueError, match='at most 1'):
        files.inputs(catalog.store, 'chat')
    assert len(files.inputs(catalog.store, 'chat', ['a.txt'])) == 1
