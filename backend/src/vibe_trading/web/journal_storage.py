"""Per-bar decision journal persistence for web tracing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiosqlite

from vibe_trading.config.settings import get_settings


@dataclass
class BarJournal:
    symbol: str
    interval: str
    open_time_ms: int
    bar_time: str
    kline: Dict[str, Any]
    phase_status: Dict[str, Any]
    decision: Optional[Dict[str, Any]]
    reports: Dict[str, Dict[str, str]]
    logs: list[Dict[str, Any]]
    updated_at: str


class DecisionJournalStorage:
    def __init__(self, database_url: Optional[str] = None):
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.db_path = self._resolve_db_path(self.database_url)

    @staticmethod
    def _resolve_db_path(database_url: str) -> str:
        if database_url.startswith("sqlite+aiosqlite:///"):
            raw_path = database_url.replace("sqlite+aiosqlite:///", "", 1)
        elif database_url.startswith("sqlite:///"):
            raw_path = database_url.replace("sqlite:///", "", 1)
        else:
            # fallback to local db for unsupported urls
            raw_path = "vibe_trading.db"

        return str(Path(raw_path).expanduser())

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bar_decision_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL,
                    bar_time TEXT NOT NULL,
                    kline_json TEXT NOT NULL,
                    phase_status_json TEXT NOT NULL,
                    decision_json TEXT,
                    reports_json TEXT NOT NULL,
                    logs_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(symbol, interval, open_time_ms)
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bar_decision_journal_symbol_interval_time
                ON bar_decision_journal(symbol, interval, open_time_ms)
                """
            )
            await conn.commit()

    async def upsert_bar(
        self,
        *,
        symbol: str,
        interval: str,
        open_time_ms: int,
        bar_time: str,
        update: Dict[str, Any],
    ) -> None:
        existing = await self.get_bar(symbol=symbol, interval=interval, open_time_ms=open_time_ms)

        if existing is None:
            payload = {
                "kline": {},
                "phase_status": {},
                "decision": None,
                "reports": {},
                "logs": [],
            }
        else:
            payload = {
                "kline": existing.kline,
                "phase_status": existing.phase_status,
                "decision": existing.decision,
                "reports": existing.reports,
                "logs": existing.logs,
            }

        if "kline" in update and update["kline"] is not None:
            payload["kline"] = update["kline"]

        if "phase_status" in update and update["phase_status"] is not None:
            payload["phase_status"] = update["phase_status"]

        if "decision" in update:
            payload["decision"] = update["decision"]

        if "report" in update and update["report"] is not None:
            report = update["report"]
            phase = report.get("phase", "") or "unknown"
            agent = report.get("agent", "") or "unknown"
            content = report.get("content", "")
            phase_bucket = payload["reports"].setdefault(phase, {})
            phase_bucket[agent] = content

        if "log" in update and update["log"] is not None:
            payload["logs"].append(update["log"])
            # bound log size per bar to keep record compact
            payload["logs"] = payload["logs"][-120:]

        updated_at = datetime.now().isoformat()

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO bar_decision_journal (
                    symbol, interval, open_time_ms, bar_time,
                    kline_json, phase_status_json, decision_json,
                    reports_json, logs_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval, open_time_ms)
                DO UPDATE SET
                    bar_time = excluded.bar_time,
                    kline_json = excluded.kline_json,
                    phase_status_json = excluded.phase_status_json,
                    decision_json = excluded.decision_json,
                    reports_json = excluded.reports_json,
                    logs_json = excluded.logs_json,
                    updated_at = excluded.updated_at
                """,
                (
                    symbol,
                    interval,
                    open_time_ms,
                    bar_time,
                    json.dumps(payload["kline"], ensure_ascii=False),
                    json.dumps(payload["phase_status"], ensure_ascii=False),
                    json.dumps(payload["decision"], ensure_ascii=False) if payload["decision"] is not None else None,
                    json.dumps(payload["reports"], ensure_ascii=False),
                    json.dumps(payload["logs"], ensure_ascii=False),
                    updated_at,
                ),
            )
            await conn.commit()

    async def get_bar(self, *, symbol: str, interval: str, open_time_ms: int) -> Optional[BarJournal]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                """
                SELECT symbol, interval, open_time_ms, bar_time,
                       kline_json, phase_status_json, decision_json,
                       reports_json, logs_json, updated_at
                FROM bar_decision_journal
                WHERE symbol = ? AND interval = ? AND open_time_ms = ?
                LIMIT 1
                """,
                (symbol, interval, open_time_ms),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        return BarJournal(
            symbol=row["symbol"],
            interval=row["interval"],
            open_time_ms=row["open_time_ms"],
            bar_time=row["bar_time"],
            kline=json.loads(row["kline_json"] or "{}"),
            phase_status=json.loads(row["phase_status_json"] or "{}"),
            decision=json.loads(row["decision_json"]) if row["decision_json"] else None,
            reports=json.loads(row["reports_json"] or "{}"),
            logs=json.loads(row["logs_json"] or "[]"),
            updated_at=row["updated_at"],
        )
