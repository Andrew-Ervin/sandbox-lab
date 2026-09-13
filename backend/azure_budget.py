"""Cumulative admission accounting. Unknown outcomes retain their reservations."""
import json
import math
import sqlite3
import time
import uuid
from pathlib import Path

RATES = {'quick': .108, 'headless': .216, 'developer': .432}


class AzureBudget:
    def __init__(self, path, *, initial=0, cutoff=150, ceiling=200, other_allowance=50):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS charges(id TEXT PRIMARY KEY, kind TEXT, amount REAL, started REAL, ended REAL);
          CREATE TABLE IF NOT EXISTS budget_meta(key TEXT PRIMARY KEY, value REAL);
        ''')
        if not math.isfinite(initial) or initial < 0: raise ValueError('Invalid initial cost')
        self.db.execute("INSERT INTO budget_meta VALUES ('initial',?) ON CONFLICT(key) DO UPDATE SET value=MAX(value,excluded.value)", (initial,))
        self.cutoff, self.ceiling, self.other_allowance = cutoff, ceiling, other_allowance
        self.path.chmod(0o600)

    def status(self):
        initial = self.db.execute("SELECT value FROM budget_meta WHERE key='initial'").fetchone()[0]
        estimated = initial + self.db.execute('SELECT COALESCE(SUM(amount),0) FROM charges').fetchone()[0]
        row = self.db.execute("SELECT value FROM budget_meta WHERE key='billed'").fetchone()
        billed = row[0] if row else 0
        # Conservative: billing can include already-counted usage. Taking max
        # avoids double-counting while retaining every in-flight reservation.
        open_reserved = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM charges WHERE ended IS NULL').fetchone()[0]
        committed = max(estimated, billed + open_reserved) + self.other_allowance
        return {'ceiling_usd': self.ceiling, 'cutoff_usd': self.cutoff,
                'estimated_and_reserved_usd': round(estimated, 6), 'billed_usd': billed,
                'other_allowance_usd': self.other_allowance, 'committed_usd': round(committed, 6),
                'available_usd': round(max(0, self.cutoff-committed), 6),
                'blocked': committed >= self.cutoff, 'hourly_rates': RATES,
                'billing_is_delayed': True, 'fixed_cost_approvals': []}

    def reserve(self, kind, amount):
        if not math.isfinite(amount) or amount <= 0: raise ValueError('Invalid cost reservation')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.status()['available_usd'] < amount:
                raise RuntimeError('The Azure test budget cannot cover this operation. Compute is paused; the $200 limit has not been increased.')
            ident = uuid.uuid4().hex
            self.db.execute('INSERT INTO charges VALUES (?,?,?,?,NULL)', (ident, kind, amount, time.time()))
            self.db.execute('COMMIT')
            return ident
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def finish(self, ident, actual=None):
        # Without authoritative completion, never release reserved money.
        row = self.db.execute('SELECT amount,ended FROM charges WHERE id=?', (ident,)).fetchone()
        if not row or row[1] is not None: return
        amount = row[0] if actual is None else max(0, float(actual))
        if not math.isfinite(amount): raise ValueError('Invalid cost')
        self.db.execute('UPDATE charges SET amount=?,ended=? WHERE id=? AND ended IS NULL', (amount, time.time(), ident))

    def refresh_billed(self, value):
        if not math.isfinite(value) or value < 0: raise ValueError('Invalid bill')
        self.db.execute("INSERT INTO budget_meta VALUES ('billed',?) ON CONFLICT(key) DO UPDATE SET value=MAX(value,excluded.value)", (value,))
