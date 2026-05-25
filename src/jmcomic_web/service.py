from __future__ import annotations

import queue
import threading
import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from jmcomic import JmOption, JmcomicText, create_option, jm_log

from .config import WebConfig
from .db import WebDatabase, _now_text
from .downloader import WebProgressDownloader
from .models import DownloadRecord, DownloadRun, DownloadRunItem
from .translate import TranslateSettings, build_translator, translate_many


@dataclass
class QueuedTask:
    run_id: str
    album_id: str
    order_index: int
    raw_input: str = ""


class DownloadManager:
    """负责批量下载、持久化状态和任务调度。"""

    def __init__(self, config: WebConfig, db: Optional[WebDatabase] = None):
        self.config = config
        self.config.ensure_paths()
        self.db = db or WebDatabase(config.db_path)
        self._queue: "queue.Queue[Optional[QueuedTask]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._workers: List[threading.Thread] = []
        self._worker_count = max(int(config.worker_count), 1)
        self._start_workers()

    # ---------- life cycle ----------

    def _start_workers(self) -> None:
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"jmcomic-web-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def shutdown(self) -> None:
        self._stop_event.set()
        for _ in self._workers:
            self._queue.put(None)
        for worker in self._workers:
            worker.join(timeout=2)

    # ---------- option / translator ----------

    def build_option(self) -> JmOption:
        """每个任务都使用独立 option，避免客户端共享导致线程问题。"""
        option_path = self.config.option_path
        if option_path:
            path = Path(option_path)
            if path.exists():
                option = create_option(str(path))
            else:
                jm_log("web.option", f"未找到 option 文件，回退到默认配置: {path}")
                option = JmOption.default()
        else:
            option = JmOption.default()

        if self.config.download_base_dir:
            base_dir = str(Path(self.config.download_base_dir).expanduser().resolve())
            option.dir_rule.base_dir = base_dir

        return option

    def build_translator(
        self,
        translate_enabled: Optional[bool] = None,
        translate_provider: Optional[str] = None,
        translate_target_lang: Optional[str] = None,
    ):
        enabled = self.config.translate_enabled if translate_enabled is None else bool(translate_enabled)
        provider = translate_provider or self.config.translate_provider
        settings = TranslateSettings(
            enabled=enabled,
            provider=provider,
            source_lang=self.config.translate_source_lang,
            target_lang=translate_target_lang or self.config.translate_target_lang,
            timeout=self.config.translate_timeout,
        )
        return build_translator(settings)

    # ---------- public query ----------

    def list_records(self, page: int = 1, page_size: Optional[int] = None, keyword: str = "") -> Dict[str, Any]:
        return self.db.list_records(page=page, page_size=page_size or self.config.page_size, keyword=keyword)

    def list_runs(self, page: int = 1, page_size: Optional[int] = None) -> Dict[str, Any]:
        return self.db.list_runs(page=page, page_size=page_size or self.config.page_size)

    def get_run_snapshot(self, run_id: str) -> Dict[str, Any]:
        self.db.refresh_run_summary(run_id)
        return self.db.build_snapshot(run_id)

    def get_record(self, album_id: str) -> Optional[DownloadRecord]:
        return self.db.get_record(album_id)

    def get_logs(self, run_id: str, limit: int = 200):
        return [asdict(item) for item in self.db.list_logs(run_id, limit=limit)]

    def fetch_cover_bytes(self, album_id: str):
        """封面预览走代理，避免前端直接跨域拉取。"""
        option = self.build_option()
        client = option.build_jm_client()
        cover_url = JmcomicText.get_album_cover_url(album_id)
        resp = client.get_jm_image(cover_url)
        resp.require_success()
        content_type = "image/jpeg"
        try:
            content_type = resp.resp.headers.get("Content-Type") or content_type
        except Exception:
            pass
        return resp.content, content_type

    # ---------- submit ----------

    def submit_batch(
        self,
        raw_ids: Iterable[str],
        *,
        note: str = "",
        translate_enabled: Optional[bool] = None,
        translate_provider: Optional[str] = None,
        translate_target_lang: Optional[str] = None,
        source: str = "ui",
    ) -> DownloadRun:
        album_ids = self._normalize_ids(raw_ids)
        run_id = uuid.uuid4().hex
        now = _now_text()
        run = DownloadRun(
            run_id=run_id,
            source=source,
            total_count=len(album_ids),
            status="queued" if album_ids else "completed",
            translate_enabled=self.config.translate_enabled if translate_enabled is None else bool(translate_enabled),
            translate_provider=translate_provider or self.config.translate_provider,
            translate_target_lang=translate_target_lang or self.config.translate_target_lang,
            note=note,
            created_at=now,
            started_at="",
            finished_at=now if not album_ids else "",
        )
        self.db.create_run(run)

        for order_index, album_id in enumerate(album_ids):
            self.db.create_run_item(
                DownloadRunItem(
                    run_id=run_id,
                    album_id=album_id,
                    order_index=order_index,
                    raw_input=album_id,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._queue.put(
                QueuedTask(
                    run_id=run_id,
                    album_id=album_id,
                    order_index=order_index,
                    raw_input=album_id,
                )
            )

        if not album_ids:
            self.db.append_log(run_id, "未提交任何有效的漫画 ID", level="warning")
        else:
            self.db.append_log(run_id, f"批量任务已进入队列，共 {len(album_ids)} 个漫画", level="info")

        self.db.refresh_run_summary(run_id)
        return self.db.get_run(run_id) or run

    def redownload(self, album_id: str, **kwargs) -> DownloadRun:
        return self.submit_batch([album_id], note="redownload", source="redownload", **kwargs)

    # ---------- internal ----------

    def _normalize_ids(self, raw_ids: Iterable[str]) -> List[str]:
        seen = set()
        result: List[str] = []

        for raw in raw_ids:
            text = str(raw).strip()
            if not text:
                continue
            try:
                album_id = JmcomicText.parse_to_jm_id(text)
            except Exception as exc:
                jm_log("web.input", f"跳过无效 ID: {text}，原因: {exc}")
                continue

            if album_id in seen:
                continue
            seen.add(album_id)
            result.append(album_id)

        return result

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            task = self._queue.get()
            if task is None:
                return
            try:
                self._process_task(task)
            finally:
                self._queue.task_done()

    @staticmethod
    def _safe_len(value) -> int:
        """兼容 jmcomic 某些实体的 None 页面数据，避免统计阶段直接报错。"""
        if value is None:
            return 0
        try:
            return len(value)
        except Exception:
            return 0

    def _process_task(self, task: QueuedTask) -> None:
        run_id = task.run_id
        album_id = task.album_id
        now = _now_text()

        self.db.mark_run_item_running(run_id, album_id)
        self.db.update_run(run_id, status="running", started_at=self.db.get_run(run_id).started_at or now)
        self.db.append_log(run_id, f"开始处理漫画 {album_id}", album_id=album_id, level="info")

        option = self.build_option()
        if self.config.download_base_dir:
            option.dir_rule.base_dir = str(Path(self.config.download_base_dir).expanduser().resolve())
        run = self.db.get_run(run_id)
        translate_enabled = run.translate_enabled if run is not None else self.config.translate_enabled
        translate_provider = run.translate_provider if run is not None else self.config.translate_provider
        translate_target_lang = run.translate_target_lang if run is not None else self.config.translate_target_lang
        translator = self.build_translator(
            translate_enabled=translate_enabled,
            translate_provider=translate_provider,
            translate_target_lang=translate_target_lang,
        )
        client = option.build_jm_client()

        try:
            album = client.get_album_detail(album_id)
            translated_name = album.name
            translated_tags: list[str] = []
            if translate_enabled:
                try:
                    translated_name, translated_tags = self._translate_album(translator, album)
                    self.db.append_log(
                        run_id,
                        f"翻译已完成，目标语言: {translate_target_lang}",
                        album_id=album_id,
                        level="info",
                    )
                except Exception as exc:
                    self.db.append_log(
                        run_id,
                        f"翻译失败，已回退原文: {exc}",
                        album_id=album_id,
                        level="warning",
                    )
                    translated_name = album.name
                    translated_tags = []
            local_path = option.dir_rule.decide_album_root_dir(album)

            existing_record = self.db.get_record(album_id)
            local_path_exists = bool(
                existing_record
                and existing_record.local_path
                and Path(existing_record.local_path).exists()
            )
            if existing_record is not None or local_path_exists:
                option.download.cache = False
                self.db.append_log(
                    run_id,
                    f"检测到本地已存在漫画 {album_id}，将覆盖下载",
                    album_id=album_id,
                    level="info",
                )

            self.db.set_run_item_metadata(
                run_id,
                album_id,
                original_name=album.name,
                translated_name=translated_name,
                local_path=local_path,
                total_photos=self._safe_len(album),
                total_images=sum(self._safe_len(photo) for photo in album or []),
            )
            self.db.upsert_record(
                DownloadRecord(
                    album_id=album.album_id,
                    original_name=album.name,
                    translated_name=translated_name,
                    cover_url=JmcomicText.get_album_cover_url(album.album_id),
                    raw_tags=list(album.tags or []),
                    translated_tags=translated_tags,
                    download_time="",
                    local_path=local_path,
                    success=False,
                    latest_status="running",
                    last_error="",
                    created_at=now,
                    updated_at=now,
                )
            )

            downloader = WebProgressDownloader(
                option,
                progress_callback=lambda event, **payload: self._handle_progress_event(run_id, album_id, event, **payload),
            )
            downloader.download_by_album_detail(album)

            if getattr(album, "skip", False):
                self.db.mark_run_item_skipped(run_id, album_id, local_path=local_path)
                self.db.upsert_record(
                    DownloadRecord(
                        album_id=album.album_id,
                        original_name=album.name,
                        translated_name=translated_name,
                        cover_url=JmcomicText.get_album_cover_url(album.album_id),
                        raw_tags=list(album.tags or []),
                        translated_tags=translated_tags,
                        download_time=_now_text(),
                        local_path=local_path,
                        success=True,
                        latest_status="skipped",
                        last_error="",
                        created_at=now,
                        updated_at=_now_text(),
                    )
                )
                self.db.append_log(run_id, f"漫画 {album_id} 已跳过", album_id=album_id, level="warning")
            elif downloader.has_download_failures:
                message = "部分下载失败"
                self.db.mark_run_item_failed(run_id, album_id, message, local_path=local_path)
                self.db.upsert_record(
                    DownloadRecord(
                        album_id=album.album_id,
                        original_name=album.name,
                        translated_name=translated_name,
                        cover_url=JmcomicText.get_album_cover_url(album.album_id),
                        raw_tags=list(album.tags or []),
                        translated_tags=translated_tags,
                        download_time=_now_text(),
                        local_path=local_path,
                        success=False,
                        latest_status="partial_failed",
                        last_error=message,
                        created_at=now,
                        updated_at=_now_text(),
                    )
                )
                self.db.append_log(run_id, f"漫画 {album_id} 下载部分失败", album_id=album_id, level="error")
            else:
                self.db.mark_run_item_success(run_id, album_id, local_path=local_path)
                self.db.upsert_record(
                    DownloadRecord(
                        album_id=album.album_id,
                        original_name=album.name,
                        translated_name=translated_name,
                        cover_url=JmcomicText.get_album_cover_url(album.album_id),
                        raw_tags=list(album.tags or []),
                        translated_tags=translated_tags,
                        download_time=_now_text(),
                        local_path=local_path,
                        success=True,
                        latest_status="success",
                        last_error="",
                        created_at=now,
                        updated_at=_now_text(),
                    )
                )
                self.db.append_log(run_id, f"漫画 {album_id} 下载完成", album_id=album_id, level="info")

        except Exception as exc:
            error = f"{exc}"
            self.db.mark_run_item_failed(run_id, album_id, error)
            try:
                cover_url = JmcomicText.get_album_cover_url(album_id)
            except Exception:
                cover_url = ""
            self.db.upsert_record(
                DownloadRecord(
                    album_id=album_id,
                    original_name="",
                    translated_name="",
                    cover_url=cover_url,
                    raw_tags=[],
                    translated_tags=[],
                    download_time=_now_text(),
                    local_path="",
                    success=False,
                    latest_status="failed",
                    last_error=error,
                    created_at=now,
                    updated_at=_now_text(),
                )
            )
            self.db.append_log(run_id, f"漫画 {album_id} 下载失败: {error}", album_id=album_id, level="error")
            self.db.append_log(run_id, traceback.format_exc(), album_id=album_id, level="error")
        finally:
            self.db.refresh_run_summary(run_id)

    def _handle_progress_event(self, run_id: str, album_id: str, event: str, **payload) -> None:
        if event == "album_start":
            photo_total = int(payload.get("photo_total", 0) or 0)
            self.db.update_run_item(run_id, album_id, status="running", total_photos=photo_total, progress=0)
            self.db.refresh_run_summary(run_id)
            return

        if event == "photo_done":
            self.db.increment_run_item_progress(run_id, album_id, photo_delta=1)
            self.db.refresh_run_summary(run_id)
            return

        if event == "image_done":
            self.db.increment_run_item_progress(run_id, album_id, image_delta=1)
            self.db.refresh_run_summary(run_id)
            return

        if event == "album_done":
            self.db.update_run_item(run_id, album_id, progress=100)
            self.db.refresh_run_summary(run_id)
            return

    def _translate_album(self, translator, album) -> tuple[str, list[str]]:
        """统一翻译标题和标签，翻译失败只回退原文。"""
        translated_name = self._safe_translate(translator, album.name)
        translated_tags = translate_many(translator, album.tags or [])
        return translated_name, translated_tags

    @staticmethod
    def _safe_translate(translator, text: str) -> str:
        if not text:
            return text
        try:
            translated = translator.translate(text)
            return translated or text
        except Exception:
            return text
