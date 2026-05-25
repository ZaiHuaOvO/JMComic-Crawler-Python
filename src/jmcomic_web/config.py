from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import json

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


def _default_instance_dir() -> Path:
    """默认把 Web 运行时文件放到仓库/工作目录下的 instance 目录。"""
    return Path.cwd() / "instance"


@dataclass
class WebConfig:
    """Web 管理界面的运行配置。"""

    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    secret_key: str = "jmcomic-web"

    # SQLite 持久化文件路径。默认使用 Flask 风格的 instance 目录。
    db_path: str = str((_default_instance_dir() / "jmcomic_web.sqlite3").resolve())

    # 可选：直接复用用户现有的 jmcomic option 文件。
    option_path: Optional[str] = None

    # 可选：覆盖下载根目录，不改原有 option 文件时可直接从这里接管。
    download_base_dir: Optional[str] = str((_default_instance_dir() / "downloads").resolve())

    # 翻译配置。翻译失败不能影响下载主流程，因此默认关闭。
    translate_enabled: bool = False
    translate_provider: str = "google"
    translate_source_lang: str = "auto"
    translate_target_lang: str = "zh-CN"
    translate_timeout: float = 10.0

    # 后台队列参数。
    worker_count: int = 1

    # 页面分页大小。
    page_size: int = 20

    # 页面标题。
    title: str = "JMComic Web"

    @classmethod
    def from_mapping(cls, data: Optional[Dict[str, Any]] = None) -> "WebConfig":
        """从字典构造配置，兼容嵌套的 YAML 结构。"""
        data = data or {}
        server = data.get("server", {}) or {}
        storage = data.get("storage", {}) or {}
        download = data.get("download", {}) or {}
        translate = data.get("translate", {}) or {}
        queue = data.get("queue", {}) or {}
        ui = data.get("ui", {}) or {}

        return cls(
            host=str(server.get("host", cls.host)),
            port=int(server.get("port", cls.port)),
            debug=bool(server.get("debug", cls.debug)),
            secret_key=str(server.get("secret_key", cls.secret_key)),
            db_path=str(storage.get("db_path", cls.db_path)),
            option_path=download.get("option_path", cls.option_path),
            download_base_dir=download.get("base_dir", cls.download_base_dir),
            translate_enabled=bool(translate.get("enabled", cls.translate_enabled)),
            translate_provider=str(translate.get("provider", cls.translate_provider)),
            translate_source_lang=str(translate.get("source_lang", cls.translate_source_lang)),
            translate_target_lang=str(translate.get("target_lang", cls.translate_target_lang)),
            translate_timeout=float(translate.get("timeout", cls.translate_timeout)),
            worker_count=int(queue.get("worker_count", cls.worker_count)),
            page_size=int(ui.get("page_size", cls.page_size)),
            title=str(ui.get("title", cls.title)),
        )

    @classmethod
    def from_file(cls, filepath: str) -> "WebConfig":
        """从 YAML 文件加载配置。"""
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        data = _load_mapping_text(text, source=filepath)
        return cls.from_mapping(data)

    def to_dict(self) -> Dict[str, Any]:
        """返回便于模板/接口输出的配置字典。"""
        return asdict(self)

    def ensure_paths(self) -> None:
        """创建持久化目录，保证开包即用。"""
        db_path = Path(self.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        if self.download_base_dir:
            Path(self.download_base_dir).mkdir(parents=True, exist_ok=True)


def load_web_config(config_path: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> WebConfig:
    """加载 Web 配置，优先级：文件 < 覆盖参数。"""
    data: Dict[str, Any] = {}

    if config_path:
        path = Path(config_path)
        if path.exists():
            data = _load_mapping_text(path.read_text(encoding="utf-8"), source=str(path))

    if overrides:
        data = _deep_merge(data, overrides)

    return WebConfig.from_mapping(data)


def _load_mapping_text(text: str, source: str = "<string>") -> Dict[str, Any]:
    """读取简单映射配置。

    优先使用 PyYAML；如果当前环境没有安装 PyYAML，则退回 JSON。
    这样 CLI/服务在最小环境下仍然能开包即用。
    """
    if yaml is not None:
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{source} 的配置顶层必须是映射对象")
        return loaded

    try:
        loaded = json.loads(text)
    except Exception as exc:
        raise RuntimeError(
            f"当前环境未安装 PyYAML，无法直接解析 YAML 配置文件 {source}。"
            f"请改用 JSON 配置，或者安装 PyYAML。原始错误: {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"{source} 的配置顶层必须是对象")
    return loaded


def _deep_merge(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典，右侧优先。"""
    result = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
