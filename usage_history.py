"""Headroom — Usage History & Statement viewer."""

import csv
import json
import os
import sqlite3
import threading
import time
import tkinter.filedialog as filedialog
from datetime import datetime, timedelta, timezone

import customtkinter as ctk

from headroom_app import (
    _APPDATA,
    _ensure_appdata,
    GREEN,
    YELLOW,
    RED,
    DIM,
    SUBTEXT,
    SURFACE2,
    MONO_FONT,
    UI_FONT,
    fmt_tokens,
    fmt_usd,
    fmt_duration,
    deep,
)

SNAPSHOT_INTERVAL_SEC = 60
DB_PATH = os.path.join(_APPDATA, "usage_history.db")


# ── Database Layer ──────────────────────────────────────────────────

class UsageHistoryDB:

    def __init__(self, db_path: str = DB_PATH):
        _ensure_appdata()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        self._init_tables()

    def _init_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts                  TEXT    NOT NULL,
                    tokens_input        INTEGER NOT NULL DEFAULT 0,
                    tokens_output       INTEGER NOT NULL DEFAULT 0,
                    tokens_saved        INTEGER NOT NULL DEFAULT 0,
                    savings_percent     REAL    NOT NULL DEFAULT 0,
                    cost_with_usd       REAL    NOT NULL DEFAULT 0,
                    savings_usd         REAL    NOT NULL DEFAULT 0,
                    cache_savings_usd   REAL    NOT NULL DEFAULT 0,
                    req_total           INTEGER NOT NULL DEFAULT 0,
                    req_cached          INTEGER NOT NULL DEFAULT 0,
                    req_rate_limited    INTEGER NOT NULL DEFAULT 0,
                    req_failed          INTEGER NOT NULL DEFAULT 0,
                    lifetime_requests   INTEGER NOT NULL DEFAULT 0,
                    lifetime_tokens_saved INTEGER NOT NULL DEFAULT 0,
                    lifetime_savings_usd REAL   NOT NULL DEFAULT 0,
                    by_model_json       TEXT    DEFAULT '{}',
                    agents_json         TEXT    DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);

                CREATE TABLE IF NOT EXISTS sessions (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_ts            TEXT    NOT NULL,
                    end_ts              TEXT    NOT NULL,
                    duration_sec        REAL    NOT NULL DEFAULT 0,
                    d_tokens_input      INTEGER NOT NULL DEFAULT 0,
                    d_tokens_output     INTEGER NOT NULL DEFAULT 0,
                    d_tokens_saved      INTEGER NOT NULL DEFAULT 0,
                    d_cost_usd          REAL    NOT NULL DEFAULT 0,
                    d_savings_usd       REAL    NOT NULL DEFAULT 0,
                    d_requests          INTEGER NOT NULL DEFAULT 0,
                    d_cached            INTEGER NOT NULL DEFAULT 0,
                    d_failed            INTEGER NOT NULL DEFAULT 0,
                    d_by_model_json     TEXT    DEFAULT '{}',
                    d_agents_json       TEXT    DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_end ON sessions(end_ts);

                CREATE TABLE IF NOT EXISTS daily_summaries (
                    date_str            TEXT    PRIMARY KEY,
                    total_requests      INTEGER NOT NULL DEFAULT 0,
                    total_tokens_in     INTEGER NOT NULL DEFAULT 0,
                    total_tokens_out    INTEGER NOT NULL DEFAULT 0,
                    total_tokens_saved  INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd      REAL    NOT NULL DEFAULT 0,
                    total_savings_usd   REAL    NOT NULL DEFAULT 0,
                    session_count       INTEGER NOT NULL DEFAULT 0,
                    by_model_json       TEXT    DEFAULT '{}'
                );
            """)

    # ── Snapshots ────────────────────────────────────────────────

    def insert_snapshot(self, ts, fields):
        with self._lock:
            cur = self._conn.execute("""
                INSERT INTO snapshots (
                    ts, tokens_input, tokens_output, tokens_saved,
                    savings_percent, cost_with_usd, savings_usd,
                    cache_savings_usd, req_total, req_cached,
                    req_rate_limited, req_failed,
                    lifetime_requests, lifetime_tokens_saved,
                    lifetime_savings_usd, by_model_json, agents_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ts,
                fields.get("tokens_input", 0),
                fields.get("tokens_output", 0),
                fields.get("tokens_saved", 0),
                fields.get("savings_percent", 0),
                fields.get("cost_with_usd", 0),
                fields.get("savings_usd", 0),
                fields.get("cache_savings_usd", 0),
                fields.get("req_total", 0),
                fields.get("req_cached", 0),
                fields.get("req_rate_limited", 0),
                fields.get("req_failed", 0),
                fields.get("lifetime_requests", 0),
                fields.get("lifetime_tokens_saved", 0),
                fields.get("lifetime_savings_usd", 0),
                json.dumps(fields.get("by_model", {})),
                json.dumps(fields.get("agents", [])),
            ))
            self._conn.commit()
            return cur.lastrowid

    def get_last_snapshot(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    # ── Sessions ─────────────────────────────────────────────────

    def upsert_session(self, session_id, start_ts, end_ts, duration, deltas):
        with self._lock:
            if session_id is not None:
                self._conn.execute("""
                    UPDATE sessions SET
                        end_ts=?, duration_sec=?,
                        d_tokens_input=?, d_tokens_output=?, d_tokens_saved=?,
                        d_cost_usd=?, d_savings_usd=?,
                        d_requests=?, d_cached=?, d_failed=?,
                        d_by_model_json=?, d_agents_json=?
                    WHERE id=?
                """, (
                    end_ts, duration,
                    deltas.get("tokens_input", 0),
                    deltas.get("tokens_output", 0),
                    deltas.get("tokens_saved", 0),
                    deltas.get("cost_usd", 0),
                    deltas.get("savings_usd", 0),
                    deltas.get("requests", 0),
                    deltas.get("cached", 0),
                    deltas.get("failed", 0),
                    json.dumps(deltas.get("by_model", {})),
                    json.dumps(deltas.get("agents", [])),
                    session_id,
                ))
                self._conn.commit()
                return session_id
            else:
                cur = self._conn.execute("""
                    INSERT INTO sessions (
                        start_ts, end_ts, duration_sec,
                        d_tokens_input, d_tokens_output, d_tokens_saved,
                        d_cost_usd, d_savings_usd,
                        d_requests, d_cached, d_failed,
                        d_by_model_json, d_agents_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    start_ts, end_ts, duration,
                    deltas.get("tokens_input", 0),
                    deltas.get("tokens_output", 0),
                    deltas.get("tokens_saved", 0),
                    deltas.get("cost_usd", 0),
                    deltas.get("savings_usd", 0),
                    deltas.get("requests", 0),
                    deltas.get("cached", 0),
                    deltas.get("failed", 0),
                    json.dumps(deltas.get("by_model", {})),
                    json.dumps(deltas.get("agents", [])),
                ))
                self._conn.commit()
                return cur.lastrowid

    # ── Daily Summaries ──────────────────────────────────────────

    def rebuild_daily_summary(self, date_str):
        with self._lock:
            start = f"{date_str}T00:00:00"
            end = f"{date_str}T23:59:59"
            row = self._conn.execute("""
                SELECT
                    COALESCE(SUM(d_requests), 0)      AS total_requests,
                    COALESCE(SUM(d_tokens_input), 0)  AS total_tokens_in,
                    COALESCE(SUM(d_tokens_output), 0) AS total_tokens_out,
                    COALESCE(SUM(d_tokens_saved), 0)  AS total_tokens_saved,
                    COALESCE(SUM(d_cost_usd), 0)      AS total_cost_usd,
                    COALESCE(SUM(d_savings_usd), 0)   AS total_savings_usd,
                    COUNT(*)                           AS session_count
                FROM sessions
                WHERE end_ts >= ? AND start_ts <= ?
            """, (start, end)).fetchone()

            self._conn.execute("""
                INSERT OR REPLACE INTO daily_summaries (
                    date_str, total_requests, total_tokens_in,
                    total_tokens_out, total_tokens_saved,
                    total_cost_usd, total_savings_usd, session_count
                ) VALUES (?,?,?,?,?,?,?,?)
            """, (
                date_str,
                row["total_requests"],
                row["total_tokens_in"],
                row["total_tokens_out"],
                row["total_tokens_saved"],
                row["total_cost_usd"],
                row["total_savings_usd"],
                row["session_count"],
            ))
            self._conn.commit()

    # ── Queries ──────────────────────────────────────────────────

    def query_sessions(self, start=None, end=None, limit=500):
        with self._lock:
            sql = "SELECT * FROM sessions WHERE 1=1"
            params = []
            if start:
                sql += " AND end_ts >= ?"
                params.append(start)
            if end:
                sql += " AND start_ts <= ?"
                params.append(end)
            sql += " ORDER BY end_ts DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def query_daily_summaries(self, start=None, end=None):
        with self._lock:
            sql = "SELECT * FROM daily_summaries WHERE 1=1"
            params = []
            if start:
                sql += " AND date_str >= ?"
                params.append(start)
            if end:
                sql += " AND date_str <= ?"
                params.append(end)
            sql += " ORDER BY date_str DESC"
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def query_monthly_totals(self):
        with self._lock:
            rows = self._conn.execute("""
                SELECT
                    substr(date_str, 1, 7) AS month,
                    SUM(total_requests) AS total_requests,
                    SUM(total_tokens_in) AS total_tokens_in,
                    SUM(total_tokens_out) AS total_tokens_out,
                    SUM(total_tokens_saved) AS total_tokens_saved,
                    SUM(total_cost_usd) AS total_cost_usd,
                    SUM(total_savings_usd) AS total_savings_usd,
                    SUM(session_count) AS session_count
                FROM daily_summaries
                GROUP BY substr(date_str, 1, 7)
                ORDER BY month DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_lifetime_totals(self):
        with self._lock:
            row = self._conn.execute("""
                SELECT
                    COALESCE(SUM(d_requests), 0)    AS requests,
                    COALESCE(SUM(d_tokens_input), 0) AS tokens_input,
                    COALESCE(SUM(d_tokens_output),0) AS tokens_output,
                    COALESCE(SUM(d_tokens_saved), 0) AS tokens_saved,
                    COALESCE(SUM(d_cost_usd), 0)    AS cost_usd,
                    COALESCE(SUM(d_savings_usd), 0) AS savings_usd,
                    COUNT(*)                         AS session_count
                FROM sessions
            """).fetchone()
            return dict(row) if row else {}

    # ── Export ────────────────────────────────────────────────────

    def export_csv(self, path, start=None, end=None):
        sessions = self.query_sessions(start, end, limit=100000)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Start", "End", "Duration",
                "Requests", "Cached", "Failed",
                "Tokens In", "Tokens Out", "Tokens Saved",
                "Cost USD", "Savings USD",
            ])
            for s in reversed(sessions):
                start_dt = _parse_ts(s["start_ts"])
                end_dt = _parse_ts(s["end_ts"])
                writer.writerow([
                    start_dt.strftime("%Y-%m-%d"),
                    start_dt.strftime("%H:%M"),
                    end_dt.strftime("%H:%M"),
                    fmt_duration(s["duration_sec"]),
                    s["d_requests"], s["d_cached"], s["d_failed"],
                    s["d_tokens_input"], s["d_tokens_output"],
                    s["d_tokens_saved"],
                    f"{s['d_cost_usd']:.4f}",
                    f"{s['d_savings_usd']:.4f}",
                ])
        return len(sessions)

    def close(self):
        with self._lock:
            self._conn.close()


# ── Snapshot Engine ─────────────────────────────────────────────────

class UsageTracker:

    def __init__(self):
        self._db = UsageHistoryDB()
        self._last_snapshot_time = 0.0
        self._baseline = None
        self._current_session_id = None
        self._session_start_ts = None
        self._last_req_total = -1
        self._last_fields = None

    def record_snapshot(self, stats, proxy_online=False):
        try:
            self._do_record(stats, proxy_online)
        except Exception:
            pass

    def _do_record(self, stats, proxy_online):
        if not stats:
            if not proxy_online and self._baseline is not None:
                self._finalize_session()
            return

        now = time.time()
        if now - self._last_snapshot_time < SNAPSHOT_INTERVAL_SEC:
            return

        fields = self._extract_fields(stats)
        req_total = fields.get("req_total", 0)

        if self._last_req_total >= 0 and req_total < self._last_req_total:
            self._finalize_session()

        if fields == self._last_fields:
            return

        ts = datetime.now(timezone.utc).isoformat()
        self._db.insert_snapshot(ts, fields)
        self._last_snapshot_time = now
        self._last_fields = fields
        self._last_req_total = req_total

        if self._baseline is None:
            self._baseline = fields.copy()
            self._session_start_ts = ts

        deltas = self._compute_deltas(fields, self._baseline)

        start = self._session_start_ts or ts
        duration = (
            _parse_ts(ts) - _parse_ts(start)
        ).total_seconds()

        self._current_session_id = self._db.upsert_session(
            self._current_session_id, start, ts, duration, deltas
        )

        date_str = _parse_ts(ts).strftime("%Y-%m-%d")
        self._db.rebuild_daily_summary(date_str)

    def _extract_fields(self, stats):
        tok = deep(stats, "tokens", fallback={})
        cost = deep(stats, "cost", fallback={})
        req = deep(stats, "requests", fallback={})
        ps = deep(stats, "persistent_savings", "lifetime", fallback={})
        wt = deep(stats, "subscription_window", "window_tokens", fallback={})
        au = deep(stats, "agent_usage", fallback={})

        return {
            "tokens_input": int(tok.get("input", 0) or 0),
            "tokens_output": int(tok.get("output", 0) or 0),
            "tokens_saved": int(
                tok.get("all_layers_saved") or tok.get("saved", 0) or 0
            ),
            "savings_percent": float(
                tok.get("all_layers_savings_percent")
                or tok.get("savings_percent", 0) or 0
            ),
            "cost_with_usd": float(cost.get("cost_with_headroom_usd", 0) or 0),
            "savings_usd": float(cost.get("savings_usd", 0) or 0),
            "cache_savings_usd": float(cost.get("cache_savings_usd", 0) or 0),
            "req_total": int(req.get("total", 0) or 0),
            "req_cached": int(req.get("cached", 0) or 0),
            "req_rate_limited": int(req.get("rate_limited", 0) or 0),
            "req_failed": int(req.get("failed", 0) or 0),
            "lifetime_requests": int(ps.get("requests", 0) or 0),
            "lifetime_tokens_saved": int(ps.get("tokens_saved", 0) or 0),
            "lifetime_savings_usd": float(
                ps.get("compression_savings_usd", 0) or 0
            ),
            "by_model": wt.get("by_model", {}),
            "agents": au.get("agents", []),
        }

    @staticmethod
    def _compute_deltas(current, baseline):
        def _d(key):
            return max(0, (current.get(key, 0) or 0) - (baseline.get(key, 0) or 0))

        return {
            "tokens_input": _d("tokens_input"),
            "tokens_output": _d("tokens_output"),
            "tokens_saved": _d("tokens_saved"),
            "cost_usd": round(
                max(0, (current.get("cost_with_usd", 0) or 0)
                    - (baseline.get("cost_with_usd", 0) or 0)), 6
            ),
            "savings_usd": round(
                max(0, (current.get("savings_usd", 0) or 0)
                    - (baseline.get("savings_usd", 0) or 0)), 6
            ),
            "requests": _d("req_total"),
            "cached": _d("req_cached"),
            "failed": _d("req_failed"),
            "by_model": current.get("by_model", {}),
            "agents": current.get("agents", []),
        }

    def _finalize_session(self):
        if self._baseline is not None and self._current_session_id is not None:
            date_str = _parse_ts(
                self._session_start_ts or datetime.now(timezone.utc).isoformat()
            ).strftime("%Y-%m-%d")
            last = self._db.get_last_snapshot()
            if last:
                deltas = self._compute_deltas(
                    self._extract_fields_from_snapshot(last), self._baseline
                )
                if deltas.get("requests", 0) > 0:
                    self._db.rebuild_daily_summary(date_str)

        self._baseline = None
        self._current_session_id = None
        self._session_start_ts = None
        self._last_req_total = -1

    @staticmethod
    def _extract_fields_from_snapshot(row):
        return {
            "tokens_input": row.get("tokens_input", 0),
            "tokens_output": row.get("tokens_output", 0),
            "tokens_saved": row.get("tokens_saved", 0),
            "cost_with_usd": row.get("cost_with_usd", 0),
            "savings_usd": row.get("savings_usd", 0),
            "req_total": row.get("req_total", 0),
            "req_cached": row.get("req_cached", 0),
            "req_failed": row.get("req_failed", 0),
            "by_model": json.loads(row.get("by_model_json", "{}")),
            "agents": json.loads(row.get("agents_json", "[]")),
        }

    def close(self):
        self._finalize_session()
        self._db.close()


# ── Statement Window UI ────────────────────────────────────────────

BG_DARK = "#1e1e2e"
ROW_ALT = "#262637"


def _parse_ts(ts_str):
    try:
        return datetime.fromisoformat(ts_str).astimezone()
    except Exception:
        return datetime.now().astimezone()


class UsageStatementWindow(ctk.CTkToplevel):

    def __init__(self, master, tracker):
        super().__init__(master)
        self.title("Headroom — Usage Statement")
        self.geometry("720x640")
        self.minsize(600, 480)

        self._tracker = tracker
        self._db = tracker._db
        self._filter_range = "30d"
        self._view_mode = "Sessions"

        self._countdown_id = None
        self._seconds_left = 60

        self._build_ui()
        self._load_data()
        self._start_countdown()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_countdown(self):
        self._seconds_left = 60
        self._tick_countdown()

    def _tick_countdown(self):
        self._countdown_label.configure(text=f"refresh in {self._seconds_left}s")
        if self._seconds_left <= 0:
            self._load_data()
            self._seconds_left = 60
        self._seconds_left -= 1
        self._countdown_id = self.after(1000, self._tick_countdown)

    def _on_close(self):
        if self._countdown_id is not None:
            self.after_cancel(self._countdown_id)
        self.destroy()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_header(self)
        self._build_filter_bar(self)
        self._build_summary_cards(self)
        self._build_statement_list(self)
        self._build_footer(self)

    # ── Header ───────────────────────────────────────────────────

    def _build_header(self, parent):
        hdr = ctk.CTkFrame(parent, fg_color="transparent", height=50)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="Usage Statement",
                     font=ctk.CTkFont(family=UI_FONT, size=20, weight="bold")
                     ).grid(row=0, column=0, sticky="w")

        self._countdown_label = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=10), text_color=DIM)
        self._countdown_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        self._date_range_label = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=11), text_color=DIM)
        self._date_range_label.grid(row=0, column=2, sticky="e")

    # ── Filter Bar ───────────────────────────────────────────────

    def _build_filter_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=4)

        self._range_seg = ctk.CTkSegmentedButton(
            bar, values=["7d", "30d", "90d", "All"],
            command=self._on_range_change)
        self._range_seg.set("30d")
        self._range_seg.pack(side="left", padx=(0, 12))

        self._view_seg = ctk.CTkSegmentedButton(
            bar, values=["Sessions", "Daily", "Monthly"],
            command=self._on_view_change)
        self._view_seg.set("Sessions")
        self._view_seg.pack(side="left")

    # ── Summary Cards ────────────────────────────────────────────

    def _build_summary_cards(self, parent):
        cards = ctk.CTkFrame(parent, corner_radius=12)
        cards.grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        cards.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._card_spent = self._make_card(cards, "$0.00", "total spent", 0)
        self._card_saved = self._make_card(cards, "$0.00", "total saved", 1)
        self._card_reqs = self._make_card(cards, "0", "requests", 2)
        self._card_sessions = self._make_card(cards, "0", "sessions", 3)

        self._projection_label = ctk.CTkLabel(
            cards, text="", font=ctk.CTkFont(size=10), text_color=SUBTEXT)
        self._projection_label.grid(
            row=1, column=0, columnspan=4, padx=12, pady=(0, 8), sticky="w")

    def _make_card(self, parent, value, label, col):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, padx=12, pady=(12, 10), sticky="nsew")

        val = ctk.CTkLabel(f, text=value,
                           font=ctk.CTkFont(size=22, weight="bold"),
                           text_color=GREEN)
        val.pack(anchor="center")

        ctk.CTkLabel(f, text=label,
                     font=ctk.CTkFont(size=10), text_color=DIM
                     ).pack(anchor="center")
        return val

    # ── Statement List ───────────────────────────────────────────

    def _build_statement_list(self, parent):
        self._scroll = ctk.CTkScrollableFrame(
            parent, corner_radius=8, fg_color="transparent")
        self._scroll.grid(row=3, column=0, sticky="nsew", padx=16, pady=4)
        self._scroll.grid_columnconfigure(0, weight=1)

    # ── Footer ───────────────────────────────────────────────────

    def _build_footer(self, parent):
        ftr = ctk.CTkFrame(parent, fg_color="transparent", height=50)
        ftr.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 12))
        ftr.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            ftr, text="Export CSV", width=110, height=30,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", border_width=1,
            border_color=DIM, text_color=SUBTEXT,
            hover_color=SURFACE2,
            command=self._export_csv,
        ).grid(row=0, column=0, sticky="w")

        self._total_label = ctk.CTkLabel(
            ftr, text="",
            font=ctk.CTkFont(family=MONO_FONT, size=11), text_color=SUBTEXT)
        self._total_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(
            ftr, text="Close", width=80, height=30,
            command=self.destroy,
        ).grid(row=0, column=2, sticky="e")

    # ── Data Loading ─────────────────────────────────────────────

    def _get_date_range(self):
        now = datetime.now()
        mapping = {"7d": 7, "30d": 30, "90d": 90}
        days = mapping.get(self._filter_range)
        if days:
            start = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
            end = now.strftime("%Y-%m-%dT23:59:59")
        else:
            start, end = None, None
        return start, end

    def _load_data(self):
        start, end = self._get_date_range()

        if start and end:
            self._date_range_label.configure(text=f"{start}  →  {end}")
        else:
            self._date_range_label.configure(text="All time")

        if self._view_mode == "Sessions":
            data = self._db.query_sessions(start, end)
            self._render_sessions(data)
        elif self._view_mode == "Daily":
            data = self._db.query_daily_summaries(start, end)
            self._render_daily(data)
        else:
            data = self._db.query_monthly_totals()
            self._render_monthly(data)

        totals = self._db.get_lifetime_totals() if not start else {}
        if start:
            if self._view_mode == "Sessions":
                totals = {
                    "cost_usd": sum(s.get("d_cost_usd", 0) for s in data),
                    "savings_usd": sum(s.get("d_savings_usd", 0) for s in data),
                    "requests": sum(s.get("d_requests", 0) for s in data),
                    "session_count": len(data),
                }
            elif self._view_mode == "Daily":
                totals = {
                    "cost_usd": sum(s.get("total_cost_usd", 0) for s in data),
                    "savings_usd": sum(s.get("total_savings_usd", 0) for s in data),
                    "requests": sum(s.get("total_requests", 0) for s in data),
                    "session_count": sum(s.get("session_count", 0) for s in data),
                }
            else:
                totals = {
                    "cost_usd": sum(s.get("total_cost_usd", 0) for s in data),
                    "savings_usd": sum(s.get("total_savings_usd", 0) for s in data),
                    "requests": sum(s.get("total_requests", 0) for s in data),
                    "session_count": sum(s.get("session_count", 0) for s in data),
                }

        cost = totals.get("cost_usd", 0)
        saved = totals.get("savings_usd", 0)
        reqs = totals.get("requests", 0)
        sess = totals.get("session_count", 0)

        self._card_spent.configure(text=fmt_usd(cost))
        self._card_saved.configure(text=fmt_usd(saved))
        self._card_reqs.configure(text=f"{int(reqs):,}")
        self._card_sessions.configure(text=f"{int(sess):,}")

        self._update_projection()

        self._total_label.configure(
            text=f"Total: {fmt_usd(cost)} spent  |  {fmt_usd(saved)} saved  |  {int(reqs):,} requests"
        )

    # ── Renderers ────────────────────────────────────────────────

    def _clear_list(self):
        for w in self._scroll.winfo_children():
            w.destroy()

    def _render_sessions(self, sessions):
        self._clear_list()

        if not sessions:
            ctk.CTkLabel(self._scroll, text="No sessions recorded yet.",
                         font=ctk.CTkFont(size=13), text_color=DIM
                         ).pack(pady=40)
            return

        current_date = None
        row_idx = 0

        for i, s in enumerate(sessions):
            end_dt = _parse_ts(s["end_ts"])
            date_str = end_dt.strftime("%b %d, %Y")

            if date_str != current_date:
                current_date = date_str
                day_total = sum(
                    x["d_cost_usd"] for x in sessions
                    if _parse_ts(x["end_ts"]).strftime("%b %d, %Y") == date_str
                )
                self._date_header(date_str, day_total, row_idx)
                row_idx += 1

            self._session_row(s, row_idx, i % 2 == 0)
            row_idx += 1

    def _date_header(self, date_str, day_total, row_idx):
        hdr = ctk.CTkFrame(self._scroll, fg_color=SURFACE2,
                           corner_radius=6, height=30)
        hdr.grid(row=row_idx, column=0, sticky="ew", pady=(8, 2), padx=2)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text=f"  {date_str}",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=8, pady=4)

        ctk.CTkLabel(hdr, text=fmt_usd(day_total),
                     font=ctk.CTkFont(family=MONO_FONT, size=11, weight="bold"),
                     anchor="e").grid(row=0, column=1, sticky="e", padx=8, pady=4)

    def _session_row(self, s, row_idx, alt):
        bg = ROW_ALT if alt else "transparent"
        row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4, height=28)
        row.grid(row=row_idx, column=0, sticky="ew", pady=1, padx=2)
        row.grid_columnconfigure(4, weight=1)

        start_dt = _parse_ts(s["start_ts"])
        end_dt = _parse_ts(s["end_ts"])
        time_range = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"

        ctk.CTkLabel(row, text=time_range,
                     font=ctk.CTkFont(family=MONO_FONT, size=11),
                     text_color=SUBTEXT, width=90, anchor="w"
                     ).grid(row=0, column=0, padx=(8, 4), pady=3)

        ctk.CTkLabel(row, text=fmt_duration(s["duration_sec"]),
                     font=ctk.CTkFont(size=10), text_color=DIM,
                     width=50, anchor="w"
                     ).grid(row=0, column=1, padx=4, pady=3)

        ctk.CTkLabel(row, text=f"{s['d_requests']} req",
                     font=ctk.CTkFont(size=10), text_color=DIM,
                     width=55, anchor="w"
                     ).grid(row=0, column=2, padx=4, pady=3)

        tokens_text = f"↓{fmt_tokens(s['d_tokens_input'])} ↑{fmt_tokens(s['d_tokens_output'])}"
        ctk.CTkLabel(row, text=tokens_text,
                     font=ctk.CTkFont(size=10), text_color=DIM,
                     anchor="w"
                     ).grid(row=0, column=3, padx=4, pady=3)

        ctk.CTkLabel(row, text="",
                     ).grid(row=0, column=4, sticky="ew")

        ctk.CTkLabel(row, text=fmt_usd(s["d_cost_usd"]),
                     font=ctk.CTkFont(family=MONO_FONT, size=11, weight="bold"),
                     width=70, anchor="e"
                     ).grid(row=0, column=5, padx=4, pady=3)

        ctk.CTkLabel(row, text=f"↓{fmt_usd(s['d_savings_usd'])}",
                     font=ctk.CTkFont(family=MONO_FONT, size=10),
                     text_color=GREEN, width=70, anchor="e"
                     ).grid(row=0, column=6, padx=(4, 8), pady=3)

    def _render_daily(self, summaries):
        self._clear_list()

        if not summaries:
            ctk.CTkLabel(self._scroll, text="No daily data yet.",
                         font=ctk.CTkFont(size=13), text_color=DIM
                         ).pack(pady=40)
            return

        for i, d in enumerate(summaries):
            bg = ROW_ALT if i % 2 == 0 else "transparent"
            row = ctk.CTkFrame(self._scroll, fg_color=bg,
                               corner_radius=4, height=32)
            row.grid(row=i, column=0, sticky="ew", pady=1, padx=2)
            row.grid_columnconfigure(3, weight=1)

            ctk.CTkLabel(row, text=d["date_str"],
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=100, anchor="w"
                         ).grid(row=0, column=0, padx=(8, 4), pady=4)

            ctk.CTkLabel(row, text=f"{d['session_count']} sessions",
                         font=ctk.CTkFont(size=10), text_color=DIM,
                         width=70, anchor="w"
                         ).grid(row=0, column=1, padx=4, pady=4)

            ctk.CTkLabel(row, text=f"{d['total_requests']:,} req",
                         font=ctk.CTkFont(size=10), text_color=DIM,
                         width=70, anchor="w"
                         ).grid(row=0, column=2, padx=4, pady=4)

            ctk.CTkLabel(row, text="",
                         ).grid(row=0, column=3, sticky="ew")

            ctk.CTkLabel(row, text=fmt_usd(d["total_cost_usd"]),
                         font=ctk.CTkFont(family=MONO_FONT, size=11, weight="bold"),
                         width=70, anchor="e"
                         ).grid(row=0, column=4, padx=4, pady=4)

            ctk.CTkLabel(row, text=f"↓{fmt_usd(d['total_savings_usd'])}",
                         font=ctk.CTkFont(family=MONO_FONT, size=10),
                         text_color=GREEN, width=70, anchor="e"
                         ).grid(row=0, column=5, padx=(4, 8), pady=4)

    def _render_monthly(self, totals):
        self._clear_list()

        if not totals:
            ctk.CTkLabel(self._scroll, text="No monthly data yet.",
                         font=ctk.CTkFont(size=13), text_color=DIM
                         ).pack(pady=40)
            return

        for i, m in enumerate(totals):
            bg = ROW_ALT if i % 2 == 0 else "transparent"
            row = ctk.CTkFrame(self._scroll, fg_color=bg,
                               corner_radius=4, height=32)
            row.grid(row=i, column=0, sticky="ew", pady=1, padx=2)
            row.grid_columnconfigure(3, weight=1)

            ctk.CTkLabel(row, text=m["month"],
                         font=ctk.CTkFont(size=13, weight="bold"),
                         width=80, anchor="w"
                         ).grid(row=0, column=0, padx=(8, 4), pady=4)

            ctk.CTkLabel(row, text=f"{m['session_count']} sessions",
                         font=ctk.CTkFont(size=10), text_color=DIM,
                         width=80, anchor="w"
                         ).grid(row=0, column=1, padx=4, pady=4)

            ctk.CTkLabel(row, text=f"{m['total_requests']:,} req",
                         font=ctk.CTkFont(size=10), text_color=DIM,
                         width=70, anchor="w"
                         ).grid(row=0, column=2, padx=4, pady=4)

            ctk.CTkLabel(row, text="",
                         ).grid(row=0, column=3, sticky="ew")

            ctk.CTkLabel(row, text=fmt_usd(m["total_cost_usd"]),
                         font=ctk.CTkFont(family=MONO_FONT, size=12, weight="bold"),
                         width=80, anchor="e"
                         ).grid(row=0, column=4, padx=4, pady=4)

            ctk.CTkLabel(row, text=f"↓{fmt_usd(m['total_savings_usd'])}",
                         font=ctk.CTkFont(family=MONO_FONT, size=11),
                         text_color=GREEN, width=80, anchor="e"
                         ).grid(row=0, column=5, padx=(4, 8), pady=4)

    # ── Event Handlers ───────────────────────────────────────────

    def _update_projection(self):
        now = datetime.now()
        month_start = now.replace(day=1).strftime("%Y-%m-%dT00:00:00")
        month_end = now.strftime("%Y-%m-%dT23:59:59")
        sessions = self._db.query_sessions(month_start, month_end, limit=100000)

        if not sessions:
            self._projection_label.configure(text="")
            return

        cost_so_far = sum(s.get("d_cost_usd", 0) for s in sessions)
        saved_so_far = sum(s.get("d_savings_usd", 0) for s in sessions)
        day_of_month = now.day

        if day_of_month < 3:
            self._projection_label.configure(
                text=f"This month so far: {fmt_usd(cost_so_far)} spent  |  {fmt_usd(saved_so_far)} saved")
            return

        import calendar
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        projected_cost = (cost_so_far / day_of_month) * days_in_month
        projected_saved = (saved_so_far / day_of_month) * days_in_month

        self._projection_label.configure(
            text=f"Projected this month: {fmt_usd(projected_cost)} spent  |  "
                 f"{fmt_usd(projected_saved)} saved  "
                 f"(based on {day_of_month} days)")

    def _on_range_change(self, value):
        self._filter_range = value
        self._load_data()
        self._seconds_left = 60

    def _on_view_change(self, value):
        self._view_mode = value
        self._load_data()
        self._seconds_left = 60

    def _export_csv(self):
        start, end = self._get_date_range()
        default_name = f"headroom-usage-{datetime.now().strftime('%Y%m%d')}.csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Usage History",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return
        count = self._db.export_csv(path, start, end)
        dialog = ctk.CTkToplevel(self)
        dialog.title("Export Complete")
        dialog.geometry("320x120")
        dialog.resizable(False, False)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text=f"Exported {count} sessions to:\n{os.path.basename(path)}",
                     font=ctk.CTkFont(size=12), wraplength=280
                     ).pack(padx=20, pady=(20, 10))
        ctk.CTkButton(dialog, text="OK", width=80,
                      command=dialog.destroy).pack(pady=(0, 12))
