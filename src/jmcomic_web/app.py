from __future__ import annotations

import json
import mimetypes
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .config import WebConfig, load_web_config
from .service import DownloadManager


class JmcomicWebApplication:
    """标准库实现的轻量 Web 管理器。"""

    def __init__(self, config: WebConfig):
        self.config = config
        self.manager = DownloadManager(config)
        self.templates_dir = Path(__file__).with_name("templates")
        self.static_dir = Path(__file__).with_name("static")
        self.httpd = _ThreadingHTTPServer((config.host, int(config.port)), _RequestHandler, self)

    def run(self) -> None:
        print(f"JMComic Web running at http://{self.config.host}:{self.config.port}")
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        self.manager.shutdown()
        self.httpd.shutdown()
        self.httpd.server_close()

    def render_template(self, filename: str) -> str:
        path = self.templates_dir / filename
        text = path.read_text(encoding="utf-8")
        return text.replace("__TITLE__", self.config.title)


def create_app(
    config: Optional[WebConfig] = None,
    *,
    config_path: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> JmcomicWebApplication:
    if config is None:
        config = load_web_config(config_path=config_path, overrides=overrides)
    return JmcomicWebApplication(config)


class _ThreadingHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, app: JmcomicWebApplication):
        super().__init__(server_address, RequestHandlerClass)
        self.app = app


class _RequestHandler(BaseHTTPRequestHandler):
    server: _ThreadingHTTPServer

    def log_message(self, format, *args):  # noqa: A003
        # 统一交给业务日志，避免标准库默认输出干扰终端。
        return

    # ---------- helpers ----------

    @property
    def app(self) -> JmcomicWebApplication:
        return self.server.app

    def _send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text: str, content_type: str = "text/html; charset=utf-8", status: int = 200) -> None:
        self._send_bytes(text.encode("utf-8"), content_type, status=status)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        self._send_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _ok(self, data: Any = None) -> None:
        self._send_json({"success": True, "data": data})

    def _error(self, message: str, status: int = 400, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {"success": False, "error": message}
        if extra:
            payload["extra"] = extra
        self._send_json(payload, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        return json.loads(raw)

    def _parse_query(self) -> Dict[str, str]:
        parsed = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

    def _path(self) -> str:
        return urllib.parse.urlparse(self.path).path

    def _match(self, pattern: str) -> Optional[re.Match[str]]:
        return re.fullmatch(pattern, self._path())

    def _serve_static(self, rel_path: str) -> None:
        path = (self.app.static_dir / rel_path).resolve()
        if not str(path).startswith(str(self.app.static_dir.resolve())) or not path.exists():
            self._error("静态文件不存在", status=404)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send_bytes(path.read_bytes(), content_type)

    def _serve_template(self, filename: str) -> None:
        self._send_text(self.app.render_template(filename))

    # ---------- routes ----------

    def do_GET(self) -> None:  # noqa: N802
        path = self._path()

        if path == "/" or path == "/index":
            self._serve_template("index.html")
            return

        if path == "/history":
            self._serve_template("history.html")
            return

        if path == "/api/health":
            self._ok({"status": "ok", "title": self.app.config.title})
            return

        if path == "/api/config":
            self._ok(self.app.config.to_dict())
            return

        if path == "/api/downloads":
            query = self._parse_query()
            page = int(query.get("page", "1"))
            page_size = int(query.get("page_size", str(self.app.config.page_size)))
            keyword = query.get("keyword", "")
            self._ok(self.app.manager.list_records(page=page, page_size=page_size, keyword=keyword))
            return

        if path == "/api/runs":
            query = self._parse_query()
            page = int(query.get("page", "1"))
            page_size = int(query.get("page_size", str(self.app.config.page_size)))
            self._ok(self.app.manager.list_runs(page=page, page_size=page_size))
            return

        if path.startswith("/api/downloads/") and path.endswith("/cover"):
            match = self._match(r"^/api/downloads/([^/]+)/cover$")
            if not match:
                self._error("参数错误", status=404)
                return
            album_id = urllib.parse.unquote(match.group(1))
            try:
                image, content_type = self.app.manager.fetch_cover_bytes(album_id)
                self._send_bytes(image, content_type)
            except Exception as exc:
                self._error(f"封面获取失败: {exc}", status=404)
            return

        if path.startswith("/api/downloads/"):
            match = self._match(r"^/api/downloads/([^/]+)$")
            if match:
                album_id = urllib.parse.unquote(match.group(1))
                record = self.app.manager.get_record(album_id)
                if record is None:
                    self._error("记录不存在", status=404)
                    return
                self._ok(asdict(record))
                return

        if path.startswith("/api/runs/") and path.endswith("/logs"):
            match = self._match(r"^/api/runs/([^/]+)/logs$")
            if not match:
                self._error("参数错误", status=404)
                return
            run_id = urllib.parse.unquote(match.group(1))
            query = self._parse_query()
            limit = int(query.get("limit", "200"))
            self._ok(self.app.manager.get_logs(run_id, limit=limit))
            return

        if path.startswith("/api/runs/"):
            match = self._match(r"^/api/runs/([^/]+)$")
            if match:
                run_id = urllib.parse.unquote(match.group(1))
                snapshot = self.app.manager.get_run_snapshot(run_id)
                if not snapshot:
                    self._error("任务不存在", status=404)
                    return
                self._ok(snapshot)
                return

        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
            return

        self._error("未找到页面", status=404)

    def do_POST(self) -> None:  # noqa: N802
        path = self._path()

        if path == "/api/downloads/batch":
            try:
                body = self._read_json_body()
            except Exception as exc:
                self._error(f"JSON 解析失败: {exc}", status=400)
                return

            raw_ids = body.get("ids", "")
            if isinstance(raw_ids, str):
                raw_ids = raw_ids.splitlines()
            elif not isinstance(raw_ids, list):
                raw_ids = [str(raw_ids)]

            run = self.app.manager.submit_batch(
                raw_ids,
                note=str(body.get("note", "")),
                translate_enabled=body.get("translate_enabled"),
                translate_provider=body.get("translate_provider"),
                translate_target_lang=body.get("translate_target_lang"),
            )
            self._ok(asdict(run))
            return

        if path.startswith("/api/downloads/") and path.endswith("/redownload"):
            match = self._match(r"^/api/downloads/([^/]+)/redownload$")
            if not match:
                self._error("参数错误", status=404)
                return

            album_id = urllib.parse.unquote(match.group(1))
            try:
                body = self._read_json_body()
            except Exception:
                body = {}

            run = self.app.manager.redownload(
                album_id,
                translate_enabled=body.get("translate_enabled"),
                translate_provider=body.get("translate_provider"),
                translate_target_lang=body.get("translate_target_lang"),
            )
            self._ok(asdict(run))
            return

        self._error("未找到接口", status=404)
