"""JMComic 的轻量化 Web 管理界面。

这里故意使用懒加载，避免仅导入配置/数据库模块时就强制加载原下载栈。
"""

from .config import WebConfig, load_web_config
from .db import WebDatabase

__version__ = "0.1.0"

__all__ = ["create_app", "WebConfig", "load_web_config", "WebDatabase", "DownloadManager"]


def create_app(*args, **kwargs):
    """延迟导入 Web 应用，避免包级导入时加载原下载栈。"""
    from .app import create_app as _create_app

    return _create_app(*args, **kwargs)


def __getattr__(name):
    if name == "DownloadManager":
        from .service import DownloadManager

        return DownloadManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
