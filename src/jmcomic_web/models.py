from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any, Dict, List, Optional

import json


def _loads_list(value: Any) -> List[str]:
    if value in (None, "", []):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        loaded = json.loads(value)
        if isinstance(loaded, list):
            return [str(v) for v in loaded]
    except Exception:
        pass
    return [str(value)]


def _dumps_list(value: Optional[List[str]]) -> str:
    return json.dumps(value or [], ensure_ascii=False)


@dataclass
class DownloadRecord:
    album_id: str
    original_name: str = ""
    translated_name: str = ""
    cover_url: str = ""
    raw_tags: List[str] = field(default_factory=list)
    translated_tags: List[str] = field(default_factory=list)
    download_time: str = ""
    local_path: str = ""
    success: bool = False
    latest_status: str = "pending"
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DownloadRecord":
        return cls(
            album_id=str(row["album_id"]),
            original_name=row.get("original_name", "") or "",
            translated_name=row.get("translated_name", "") or "",
            cover_url=row.get("cover_url", "") or "",
            raw_tags=_loads_list(row.get("raw_tags_json")),
            translated_tags=_loads_list(row.get("translated_tags_json")),
            download_time=row.get("download_time", "") or "",
            local_path=row.get("local_path", "") or "",
            success=bool(row.get("success", 0)),
            latest_status=row.get("latest_status", "pending") or "pending",
            last_error=row.get("last_error", "") or "",
            created_at=row.get("created_at", "") or "",
            updated_at=row.get("updated_at", "") or "",
        )

    def to_db_dict(self) -> Dict[str, Any]:
        return {
            "album_id": self.album_id,
            "original_name": self.original_name,
            "translated_name": self.translated_name,
            "cover_url": self.cover_url,
            "raw_tags_json": _dumps_list(self.raw_tags),
            "translated_tags_json": _dumps_list(self.translated_tags),
            "download_time": self.download_time,
            "local_path": self.local_path,
            "success": 1 if self.success else 0,
            "latest_status": self.latest_status,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DownloadRun:
    run_id: str
    source: str = "ui"
    total_count: int = 0
    completed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    progress_percent: int = 0
    status: str = "pending"
    translate_enabled: bool = False
    translate_provider: str = "google"
    translate_target_lang: str = "zh-CN"
    note: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    last_error: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DownloadRun":
        return cls(
            run_id=str(row["run_id"]),
            source=row.get("source", "ui") or "ui",
            total_count=int(row.get("total_count", 0) or 0),
            completed_count=int(row.get("completed_count", 0) or 0),
            success_count=int(row.get("success_count", 0) or 0),
            failed_count=int(row.get("failed_count", 0) or 0),
            progress_percent=int(row.get("progress_percent", 0) or 0),
            status=row.get("status", "pending") or "pending",
            translate_enabled=bool(row.get("translate_enabled", 0)),
            translate_provider=row.get("translate_provider", "google") or "google",
            translate_target_lang=row.get("translate_target_lang", "zh-CN") or "zh-CN",
            note=row.get("note", "") or "",
            created_at=row.get("created_at", "") or "",
            started_at=row.get("started_at", "") or "",
            finished_at=row.get("finished_at", "") or "",
            last_error=row.get("last_error", "") or "",
            updated_at=row.get("updated_at", "") or "",
        )


@dataclass
class DownloadRunItem:
    run_id: str
    album_id: str
    order_index: int = 0
    raw_input: str = ""
    original_name: str = ""
    translated_name: str = ""
    status: str = "pending"
    progress: int = 0
    total_photos: int = 0
    completed_photos: int = 0
    total_images: int = 0
    completed_images: int = 0
    local_path: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DownloadRunItem":
        return cls(
            run_id=str(row["run_id"]),
            album_id=str(row["album_id"]),
            order_index=int(row.get("order_index", 0) or 0),
            raw_input=row.get("raw_input", "") or "",
            original_name=row.get("original_name", "") or "",
            translated_name=row.get("translated_name", "") or "",
            status=row.get("status", "pending") or "pending",
            progress=int(row.get("progress", 0) or 0),
            total_photos=int(row.get("total_photos", 0) or 0),
            completed_photos=int(row.get("completed_photos", 0) or 0),
            total_images=int(row.get("total_images", 0) or 0),
            completed_images=int(row.get("completed_images", 0) or 0),
            local_path=row.get("local_path", "") or "",
            error=row.get("error", "") or "",
            created_at=row.get("created_at", "") or "",
            updated_at=row.get("updated_at", "") or "",
        )


@dataclass
class DownloadLog:
    run_id: str
    album_id: str
    level: str
    message: str
    created_at: str

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "DownloadLog":
        return cls(
            run_id=str(row["run_id"]),
            album_id=row.get("album_id", "") or "",
            level=row.get("level", "info") or "info",
            message=row.get("message", "") or "",
            created_at=row.get("created_at", "") or "",
        )
