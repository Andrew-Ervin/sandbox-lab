"""Bounded, conversation-scoped inputs. Code never reads the host filesystem."""
from .limits import value
import base64
import errno
import os
import stat
from contextlib import ExitStack
from .config import STATE


def _read_artifact(state_fd, run_id, name, remaining):
    """Pin every untrusted path component and bound reads even if a file grows."""
    if any(not isinstance(part, str) or part in ('', '.', '..') or
           any(c in part for c in ('/', '\\', '\x00')) for part in (run_id, name)):
        raise ValueError('Invalid conversation file path')
    with ExitStack() as opened:
        parent = state_fd
        try:
            for part in ('artifacts', run_id):
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                opened.callback(os.close, parent)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            opened.callback(os.close, fd)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                return None
            raise
        info = os.fstat(fd)
        maximum = value('ARTIFACT_MAX_FILE_BYTES')
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            return None
        if info.st_size > remaining:
            raise ValueError('Inputs exceed the configured total byte limit; select fewer files')
        chunks = []
        size = 0
        limit = min(maximum, remaining)
        while chunk := os.read(fd, min(65536, limit + 1 - size)):
            size += len(chunk)
            if size > maximum:
                return None
            if size > remaining:
                raise ValueError('Inputs exceed the configured total byte limit; select fewer files')
            chunks.append(chunk)
        return b''.join(chunks)


def inputs(store, thread_id, names=None):
    available = store.files(thread_id)
    if names is not None:
        if not isinstance(names, list) or len(names)>value('ARTIFACT_MAX_FILES') or any(not isinstance(n,str) for n in names):
            raise ValueError(f"Choose at most {value('ARTIFACT_MAX_FILES')} conversation files")
        available = [f for f in available if f['name'] in names]
        if set(names) != {f['name'] for f in available}: raise ValueError('Input file is not in this conversation')
    if len(available) > value('ARTIFACT_MAX_FILES'):
        raise ValueError(f"Choose at most {value('ARTIFACT_MAX_FILES')} conversation files")
    if not available:
        return []
    result=[]; size=0
    state_fd = os.open(STATE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for f in available:
            raw = _read_artifact(state_fd, f['run_id'], f['name'], value('ARTIFACT_MAX_TOTAL_BYTES') - size)
            if raw is None:
                continue
            size+=len(raw)
            result.append({'name':f['name'],'data':base64.b64encode(raw).decode()})
    finally:
        os.close(state_fd)
    return result
