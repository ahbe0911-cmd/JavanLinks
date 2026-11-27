"""Versioned JSON catalog, atomic writes and safe restore; no Qt dependency."""
from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from .catalog import Link, SAMPLE_LINKS

SCHEMA = 1
MAX_BYTES = 8 * 1024 * 1024
MAX_LINKS = 5000


@dataclass(frozen=True)
class State:
    links: tuple[Link, ...] = SAMPLE_LINKS
    sidebar_collapsed: bool = False

    def __post_init__(self):
        if len(self.links) > MAX_LINKS or len({x.id for x in self.links}) != len(self.links):
            raise ValueError('Too many links or duplicate IDs')
        if type(self.sidebar_collapsed) is not bool:
            raise ValueError('Invalid sidebar setting')


def encode(state: State) -> bytes:
    raw = (json.dumps({'schema_version': SCHEMA, 'links': [asdict(x) for x in state.links],
                       'settings': {'sidebar_collapsed': state.sidebar_collapsed}},
                      ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('Catalog exceeds size limit')
    return raw


def decode(raw: bytes) -> State:
    if len(raw) > MAX_BYTES:
        raise ValueError('Backup exceeds size limit')
    obj = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(obj, dict) or type(obj.get('schema_version')) is not int or obj['schema_version'] != SCHEMA:
        raise ValueError('Unsupported backup format')
    rows = obj.get('links')
    settings = obj.get('settings', {})
    if not isinstance(rows, list) or len(rows) > MAX_LINKS or not isinstance(settings, dict):
        raise ValueError('Invalid catalog structure')
    allowed = {'id', 'title', 'url', 'category', 'description', 'kind'}
    for row in rows:
        if not isinstance(row, dict) or not {'id', 'title', 'url', 'category'} <= row.keys() or not row.keys() <= allowed:
            raise ValueError('Invalid link record')
    return State(tuple(Link(**row) for row in rows), settings.get('sidebar_collapsed', False))


def read_state(path: Path) -> State:
    with path.open('rb') as stream:
        return decode(stream.read(MAX_BYTES + 1))


def atomic_write(path: Path, raw: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.javan-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class CatalogStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.state = read_state(self.path) if self.path.exists() else State()
        if not self.path.exists():
            atomic_write(self.path, encode(self.state))

    def _commit(self, state: State):
        atomic_write(self.path, encode(state))
        self.state = state

    def add(self, link: Link):
        self._commit(replace(self.state, links=self.state.links + (link,)))

    def edit(self, link: Link):
        if not any(x.id == link.id for x in self.state.links):
            raise ValueError('Link not found')
        self._commit(replace(self.state, links=tuple(link if x.id == link.id else x for x in self.state.links)))

    def delete(self, link_id: str):
        if not any(x.id == link_id for x in self.state.links):
            raise ValueError('Link not found')
        self._commit(replace(self.state, links=tuple(x for x in self.state.links if x.id != link_id)))

    def set_sidebar(self, collapsed: bool):
        self._commit(replace(self.state, sidebar_collapsed=collapsed))

    def export(self, path: Path):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('Choose a different backup destination')
        atomic_write(Path(path), encode(self.state))

    def restore(self, state: State):
        raw = encode(state)
        atomic_write(self.path.with_suffix('.previous.json'), encode(self.state))
        atomic_write(self.path, raw)
        self.state = state
