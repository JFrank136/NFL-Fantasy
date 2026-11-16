"""Storage: Supabase is authoritative; every write is also mirrored to a local CSV
(DATA_ROOT/expert_eval/<table>.csv, rewritten from the merged table each time) for
backup/debugging. All writes are upserts on a natural key, so reruns are idempotent;
nothing here deletes rows.

`Store(local_only=True)` skips Supabase entirely (tests / offline runs)."""
import math
import os
from pathlib import Path

import pandas as pd
import requests

from src import paths

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = paths.DATA_ROOT / "expert_eval"

KEYS = {
    "expert_eval_config": ["version"],
    "expert_eval_results": ["season", "week", "canonical_name", "position"],
    "expert_eval_snapshots": ["season", "week", "source", "scoring", "canonical_name", "position"],
    "expert_eval_pool": ["season", "week", "scoring", "canonical_name", "position", "config_version"],
    "expert_eval_scores": ["season", "week", "source", "scoring", "config_version", "position", "tier", "metric"],
    "expert_eval_weights": ["season", "week", "scoring", "weight_set", "source", "position", "tier", "config_version"],
    "expert_eval_backtests": ["run_id"],
    "expert_eval_runs": ["run_id"],
}
CHUNK = 500


def _load_env() -> None:
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _clean(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


class Store:
    def __init__(self, local_only: bool = False):
        self.local_only = local_only
        _load_env()
        self.url = os.environ.get("SUPABASE_URL")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not local_only and not (self.url and self.key):
            raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set (in-season/.env).")
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # -- low level ---------------------------------------------------------
    def _headers(self, **extra):
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        h.update(extra)
        return h

    def upsert(self, table: str, rows) -> int:
        rows = [{k: _clean(v) for k, v in r.items()} for r in (rows.to_dict("records") if isinstance(rows, pd.DataFrame) else rows)]
        if not rows:
            return 0
        if not self.local_only:
            on = ",".join(KEYS[table])
            for i in range(0, len(rows), CHUNK):
                r = requests.post(f"{self.url}/rest/v1/{table}", params={"on_conflict": on},
                                  headers=self._headers(Prefer="resolution=merge-duplicates,return=minimal"),
                                  json=rows[i:i + CHUNK], timeout=60)
                if not r.ok:
                    raise RuntimeError(f"upsert {table} failed {r.status_code}: {r.text[:300]}")
        self._mirror(table, rows)
        return len(rows)

    def insert_missing(self, table: str, rows) -> int:
        """Insert-only: rows whose natural key already exists are left untouched (frozen evidence)."""
        rows = [{k: _clean(v) for k, v in r.items()} for r in (rows.to_dict("records") if isinstance(rows, pd.DataFrame) else rows)]
        if not rows:
            return 0
        if not self.local_only:
            on = ",".join(KEYS[table])
            for i in range(0, len(rows), CHUNK):
                r = requests.post(f"{self.url}/rest/v1/{table}", params={"on_conflict": on},
                                  headers=self._headers(Prefer="resolution=ignore-duplicates,return=minimal"),
                                  json=rows[i:i + CHUNK], timeout=60)
                if not r.ok:
                    raise RuntimeError(f"insert {table} failed {r.status_code}: {r.text[:300]}")
        self._mirror(table, rows, keep="first")
        return len(rows)

    def select(self, table: str, **eq) -> pd.DataFrame:
        """All rows matching equality filters, paginated past PostgREST's 1000-row cap."""
        if self.local_only:
            p = EXPORT_DIR / f"{table}.csv"
            df = pd.read_csv(p) if p.exists() else pd.DataFrame()
            for k, v in eq.items():
                if k in df:
                    df = df[df[k] == v]
            return df.reset_index(drop=True)
        out, off = [], 0
        params = {k: f"eq.{v}" for k, v in eq.items()}
        while True:
            r = requests.get(f"{self.url}/rest/v1/{table}", params=params,
                             headers=self._headers(Range=f"{off}-{off + 999}", **{"Range-Unit": "items"}), timeout=60)
            r.raise_for_status()
            part = r.json()
            out += part
            if len(part) < 1000:
                break
            off += 1000
        return pd.DataFrame(out)

    # -- local mirror ------------------------------------------------------
    def _mirror(self, table: str, rows: list, keep: str = "last") -> None:
        p = EXPORT_DIR / f"{table}.csv"
        new = pd.DataFrame(rows)
        if p.exists():
            old = pd.read_csv(p)
            keys = KEYS[table]
            merged = pd.concat([old, new], ignore_index=True)
            for c in keys:
                if c in merged and merged[c].dtype == object:
                    merged[c] = merged[c].astype(str)
            merged = merged.drop_duplicates(subset=keys, keep=keep)
        else:
            merged = new
        tmp = p.with_suffix(".csv.tmp")
        merged.to_csv(tmp, index=False)
        tmp.replace(p)
