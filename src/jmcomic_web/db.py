from __future__ import annotations

import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .models import DownloadLog, DownloadRecord, DownloadRun, DownloadRunItem


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class WebDatabase:
    """SQLite 持久化层。

    只使用标准库，保证开包即用，不依赖外部数据库服务。
    """

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row) if row is not None else {}

    def init_schema(self) -> None:
        """初始化表结构，程序启动即可自动建表。"""
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS download_records (
                        album_id TEXT PRIMARY KEY,
                        original_name TEXT NOT NULL DEFAULT '',
                        translated_name TEXT NOT NULL DEFAULT '',
                        cover_url TEXT NOT NULL DEFAULT '',
                        raw_tags_json TEXT NOT NULL DEFAULT '[]',
                        translated_tags_json TEXT NOT NULL DEFAULT '[]',
                        download_time TEXT NOT NULL DEFAULT '',
                        local_path TEXT NOT NULL DEFAULT '',
                        success INTEGER NOT NULL DEFAULT 0,
                        latest_status TEXT NOT NULL DEFAULT 'pending',
                        last_error TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL DEFAULT ''
                    );

                    CREATE TABLE IF NOT EXISTS download_runs (
                        run_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL DEFAULT 'ui',
                        total_count INTEGER NOT NULL DEFAULT 0,
                        completed_count INTEGER NOT NULL DEFAULT 0,
                        success_count INTEGER NOT NULL DEFAULT 0,
                        failed_count INTEGER NOT NULL DEFAULT 0,
                        progress_percent INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'pending',
                        translate_enabled INTEGER NOT NULL DEFAULT 0,
                        translate_provider TEXT NOT NULL DEFAULT 'google',
                        translate_target_lang TEXT NOT NULL DEFAULT 'zh-CN',
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL DEFAULT '',
                        finished_at TEXT NOT NULL DEFAULT '',
                        last_error TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL DEFAULT ''
                    );

                    CREATE TABLE IF NOT EXISTS download_run_items (
                        run_id TEXT NOT NULL,
                        album_id TEXT NOT NULL,
                        order_index INTEGER NOT NULL DEFAULT 0,
                        raw_input TEXT NOT NULL DEFAULT '',
                        original_name TEXT NOT NULL DEFAULT '',
                        translated_name TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'pending',
                        progress INTEGER NOT NULL DEFAULT 0,
                        total_photos INTEGER NOT NULL DEFAULT 0,
                        completed_photos INTEGER NOT NULL DEFAULT 0,
                        total_images INTEGER NOT NULL DEFAULT 0,
                        completed_images INTEGER NOT NULL DEFAULT 0,
                        local_path TEXT NOT NULL DEFAULT '',
                        error TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (run_id, album_id),
                        FOREIGN KEY (run_id) REFERENCES download_runs(run_id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS download_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL,
                        album_id TEXT NOT NULL DEFAULT '',
                        level TEXT NOT NULL DEFAULT 'info',
                        message TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (run_id) REFERENCES download_runs(run_id) ON DELETE CASCADE
                    );

                    CREATE INDEX IF NOT EXISTS idx_download_records_updated_at
                    ON download_records(updated_at DESC);

                    CREATE INDEX IF NOT EXISTS idx_download_run_items_run_id
                    ON download_run_items(run_id, order_index);

                    CREATE INDEX IF NOT EXISTS idx_download_logs_run_id
                    ON download_logs(run_id, id DESC);
                    """
                )
                self._ensure_column(conn, "download_runs", "updated_at", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(conn, "download_runs", "translate_target_lang", "TEXT NOT NULL DEFAULT 'zh-CN'")
                self._ensure_column(conn, "download_run_items", "updated_at", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(conn, "download_records", "updated_at", "TEXT NOT NULL DEFAULT ''")
                self._normalize_existing_record_schema(conn)
                conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        """为旧数据库做轻量迁移，避免用户删库重来。"""
        cur = conn.execute(f"PRAGMA table_info({table})")
        columns = {str(row["name"]) for row in cur.fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _normalize_existing_record_schema(self, conn: sqlite3.Connection) -> None:
        """确保历史记录以 album_id 为唯一键，避免同 ID 重复插入。"""
        conn.execute("DELETE FROM download_records WHERE album_id IS NULL OR album_id = ''")

    def _execute(self, sql: str, params: Tuple[Any, ...] = ()) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur.lastrowid or 0

    def _execute_many(self, sql: str, rows: Iterable[Tuple[Any, ...]]) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executemany(sql, rows)
                conn.commit()

    def _fetch_one(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                row = cur.fetchone()
                return self._row_to_dict(row) if row else None

    def _fetch_all(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(sql, params)
                return [self._row_to_dict(row) for row in cur.fetchall()]

    # ---------- records ----------

    def get_record(self, album_id: str) -> Optional[DownloadRecord]:
        row = self._fetch_one(
            "SELECT * FROM download_records WHERE album_id = ?",
            (str(album_id),),
        )
        return DownloadRecord.from_row(row) if row else None

    def upsert_record(self, record: DownloadRecord) -> None:
        now = _now_text()
        existing = self.get_record(record.album_id)
        payload = record.to_db_dict()
        payload["created_at"] = existing.created_at if existing and existing.created_at else (record.created_at or now)
        payload["updated_at"] = now

        columns = [
            "album_id",
            "original_name",
            "translated_name",
            "cover_url",
            "raw_tags_json",
            "translated_tags_json",
            "download_time",
            "local_path",
            "success",
            "latest_status",
            "last_error",
            "created_at",
            "updated_at",
        ]

        updates = [
            "original_name=excluded.original_name",
            "translated_name=excluded.translated_name",
            "cover_url=excluded.cover_url",
            "raw_tags_json=excluded.raw_tags_json",
            "translated_tags_json=excluded.translated_tags_json",
            "download_time=excluded.download_time",
            "local_path=excluded.local_path",
            "success=excluded.success",
            "latest_status=excluded.latest_status",
            "last_error=excluded.last_error",
            "updated_at=excluded.updated_at",
        ]

        sql = (
            f"INSERT INTO download_records ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)}) "
            f"ON CONFLICT(album_id) DO UPDATE SET {', '.join(updates)}"
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, payload)
                conn.commit()

    def list_records(self, page: int = 1, page_size: int = 20, keyword: str = "") -> Dict[str, Any]:
        page = max(int(page), 1)
        page_size = max(int(page_size), 1)
        offset = (page - 1) * page_size

        params: List[Any] = []
        where_sql = ""
        if keyword:
            like = f"%{keyword}%"
            where_sql = (
                "WHERE album_id LIKE ? OR original_name LIKE ? OR translated_name LIKE ? "
                "OR raw_tags_json LIKE ? OR translated_tags_json LIKE ?"
            )
            params.extend([like, like, like, like, like])

        total_row = self._fetch_one(
            f"SELECT COUNT(*) AS total FROM download_records {where_sql}",
            tuple(params),
        ) or {"total": 0}

        rows = self._fetch_all(
            f"SELECT * FROM download_records {where_sql} ORDER BY updated_at DESC, album_id DESC LIMIT ? OFFSET ?",
            tuple(params + [page_size, offset]),
        )

        return {
            "items": [asdict(DownloadRecord.from_row(row)) for row in rows],
            "total": int(total_row.get("total", 0)),
            "page": page,
            "page_size": page_size,
        }

    # ---------- runs ----------

    def create_run(self, run: DownloadRun) -> None:
        payload = asdict(run)
        columns = list(payload.keys())
        sql = (
            f"INSERT INTO download_runs ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})"
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, payload)
                conn.commit()

    def get_run(self, run_id: str) -> Optional[DownloadRun]:
        row = self._fetch_one(
            "SELECT * FROM download_runs WHERE run_id = ?",
            (str(run_id),),
        )
        return DownloadRun.from_row(row) if row else None

    def list_runs(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        page = max(int(page), 1)
        page_size = max(int(page_size), 1)
        offset = (page - 1) * page_size

        total_row = self._fetch_one("SELECT COUNT(*) AS total FROM download_runs") or {"total": 0}
        rows = self._fetch_all(
            "SELECT * FROM download_runs ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?",
            (page_size, offset),
        )

        return {
            "items": [asdict(DownloadRun.from_row(row)) for row in rows],
            "total": int(total_row.get("total", 0)),
            "page": page,
            "page_size": page_size,
        }

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return

        payload = dict(fields)
        payload["run_id"] = str(run_id)
        payload.setdefault("updated_at", _now_text())
        set_keys = list(fields.keys())
        if "updated_at" not in set_keys:
            set_keys.append("updated_at")
        set_clause = ", ".join([f"{key} = :{key}" for key in set_keys])
        sql = f"UPDATE download_runs SET {set_clause} WHERE run_id = :run_id"
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, payload)
                conn.commit()

    def refresh_run_summary(self, run_id: str) -> Optional[DownloadRun]:
        summary = self._fetch_one(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN status IN ('success', 'failed', 'skipped') THEN 1 ELSE 0 END) AS completed_count,
                SUM(progress) AS progress_sum
            FROM download_run_items
            WHERE run_id = ?
            """,
            (str(run_id),),
        ) or {"total": 0, "success_count": 0, "failed_count": 0, "completed_count": 0}

        run = self.get_run(run_id)
        if run is None:
            return None

        total = int(summary.get("total", 0) or 0)
        completed = int(summary.get("completed_count", 0) or 0)
        success = int(summary.get("success_count", 0) or 0)
        failed = int(summary.get("failed_count", 0) or 0)
        progress_sum = int(summary.get("progress_sum", 0) or 0)

        status = run.status
        finished_at = run.finished_at
        started_at = run.started_at
        now = _now_text()
        if total == 0:
            status = "completed"
            finished_at = now
            started_at = started_at or now
            progress_percent = 100
        elif completed >= total:
            if failed > 0 and success > 0:
                status = "completed_with_errors"
            elif failed > 0:
                status = "failed"
            else:
                status = "completed"
            finished_at = now
            started_at = started_at or now
            progress_percent = 100
        elif completed > 0:
            status = "running"
            started_at = started_at or now
            progress_percent = min(99, int(progress_sum / max(total, 1))) if total > 0 else 0
        else:
            status = "queued"
            progress_percent = min(99, int(progress_sum / max(total, 1))) if total > 0 else 0

        self.update_run(
            run_id,
            total_count=total,
            completed_count=completed,
            success_count=success,
            failed_count=failed,
            progress_percent=progress_percent,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
        )
        return self.get_run(run_id)

    # ---------- run items ----------

    def create_run_item(self, item: DownloadRunItem) -> None:
        payload = asdict(item)
        columns = list(payload.keys())
        sql = (
            f"INSERT INTO download_run_items ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})"
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, payload)
                conn.commit()

    def get_run_item(self, run_id: str, album_id: str) -> Optional[DownloadRunItem]:
        row = self._fetch_one(
            "SELECT * FROM download_run_items WHERE run_id = ? AND album_id = ?",
            (str(run_id), str(album_id)),
        )
        return DownloadRunItem.from_row(row) if row else None

    def list_run_items(self, run_id: str) -> List[DownloadRunItem]:
        rows = self._fetch_all(
            "SELECT * FROM download_run_items WHERE run_id = ? ORDER BY order_index ASC, album_id ASC",
            (str(run_id),),
        )
        return [DownloadRunItem.from_row(row) for row in rows]

    def update_run_item(self, run_id: str, album_id: str, **fields: Any) -> None:
        if not fields:
            return

        payload = dict(fields)
        payload["run_id"] = str(run_id)
        payload["album_id"] = str(album_id)
        payload.setdefault("updated_at", _now_text())
        set_keys = list(fields.keys())
        if "updated_at" not in set_keys:
            set_keys.append("updated_at")
        set_clause = ", ".join([f"{key} = :{key}" for key in set_keys])
        sql = "UPDATE download_run_items SET " + set_clause + " WHERE run_id = :run_id AND album_id = :album_id"
        with self._lock:
            with self._connect() as conn:
                conn.execute(sql, payload)
                conn.commit()

    def increment_run_item_progress(
        self,
        run_id: str,
        album_id: str,
        *,
        photo_delta: int = 0,
        image_delta: int = 0,
    ) -> Optional[DownloadRunItem]:
        """在数据库里原子地推进进度。"""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT total_photos, completed_photos, total_images, completed_images FROM download_run_items WHERE run_id = ? AND album_id = ?",
                    (str(run_id), str(album_id)),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                total_photos = int(row["total_photos"] or 0)
                completed_photos = int(row["completed_photos"] or 0) + int(photo_delta or 0)
                total_images = int(row["total_images"] or 0)
                completed_images = int(row["completed_images"] or 0) + int(image_delta or 0)

                if total_photos <= 0:
                    progress = 0
                else:
                    progress = min(99, int((completed_photos / total_photos) * 99))

                conn.execute(
                    """
                    UPDATE download_run_items
                    SET completed_photos = ?,
                        completed_images = ?,
                        progress = ?,
                        updated_at = ?
                    WHERE run_id = ? AND album_id = ?
                    """,
                    (
                        completed_photos,
                        completed_images,
                        progress,
                        _now_text(),
                        str(run_id),
                        str(album_id),
                    ),
                )
                conn.commit()

        return self.get_run_item(run_id, album_id)

    def mark_run_item_running(self, run_id: str, album_id: str) -> None:
        self.update_run_item(
            run_id,
            album_id,
            status="running",
        )

    def mark_run_item_success(self, run_id: str, album_id: str, local_path: str = "") -> None:
        self.update_run_item(
            run_id,
            album_id,
            status="success",
            progress=100,
            local_path=local_path,
            error="",
        )

    def mark_run_item_failed(self, run_id: str, album_id: str, error: str, local_path: str = "") -> None:
        self.update_run_item(
            run_id,
            album_id,
            status="failed",
            progress=100 if local_path else 0,
            local_path=local_path,
            error=error,
        )

    def mark_run_item_skipped(self, run_id: str, album_id: str, local_path: str = "") -> None:
        self.update_run_item(
            run_id,
            album_id,
            status="skipped",
            progress=100,
            local_path=local_path,
            error="",
        )

    def set_run_item_metadata(
        self,
        run_id: str,
        album_id: str,
        *,
        original_name: str = "",
        translated_name: str = "",
        local_path: str = "",
        total_photos: int = 0,
        total_images: int = 0,
    ) -> None:
        self.update_run_item(
            run_id,
            album_id,
            original_name=original_name,
            translated_name=translated_name,
            local_path=local_path,
            total_photos=total_photos,
            total_images=total_images,
        )

    # ---------- logs ----------

    def append_log(self, run_id: str, message: str, *, album_id: str = "", level: str = "info") -> None:
        self._execute(
            """
            INSERT INTO download_logs (run_id, album_id, level, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(run_id), str(album_id), str(level), str(message), _now_text()),
        )

    def list_logs(self, run_id: str, limit: int = 200) -> List[DownloadLog]:
        rows = self._fetch_all(
            "SELECT * FROM download_logs WHERE run_id = ? ORDER BY id DESC LIMIT ?",
            (str(run_id), max(int(limit), 1)),
        )
        rows.reverse()
        return [DownloadLog.from_row(row) for row in rows]

    # ---------- convenience ----------

    def build_snapshot(self, run_id: str) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            return {}

        return {
            "run": asdict(run),
            "items": [asdict(item) for item in self.list_run_items(run_id)],
            "logs": [asdict(log) for log in self.list_logs(run_id)],
        }
