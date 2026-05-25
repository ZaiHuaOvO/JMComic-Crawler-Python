from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .app import create_app


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jmcomic-web", description="JMComic 轻量 Web 管理界面")
    parser.add_argument("--config", type=str, default=_get_env("JM_WEB_CONFIG_PATH"))
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--db-path", type=str, default=None)
    parser.add_argument("--option-path", type=str, default=None)
    parser.add_argument("--base-dir", type=str, default=None)
    parser.add_argument("--translate-enabled", action="store_true")
    parser.add_argument("--translate-provider", type=str, default=None)
    parser.add_argument("--translate-target-lang", type=str, default=None)
    parser.add_argument("--workers", type=int, default=None)
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    overrides: Dict[str, Any] = {}
    if args.host or args.port or args.debug:
        overrides.setdefault("server", {})
        if args.host:
            overrides["server"]["host"] = args.host
        if args.port:
            overrides["server"]["port"] = args.port
        if args.debug:
            overrides["server"]["debug"] = True

    if args.db_path:
        overrides.setdefault("storage", {})
        overrides["storage"]["db_path"] = str(Path(args.db_path).expanduser())

    if args.option_path or args.base_dir:
        overrides.setdefault("download", {})
        if args.option_path:
            overrides["download"]["option_path"] = str(Path(args.option_path).expanduser())
        if args.base_dir:
            overrides["download"]["base_dir"] = str(Path(args.base_dir).expanduser())

    if args.translate_enabled or args.translate_provider:
        overrides.setdefault("translate", {})
        if args.translate_enabled:
            overrides["translate"]["enabled"] = True
        if args.translate_provider:
            overrides["translate"]["provider"] = args.translate_provider
        if args.translate_target_lang:
            overrides["translate"]["target_lang"] = args.translate_target_lang
    elif args.translate_target_lang:
        overrides.setdefault("translate", {})
        overrides["translate"]["target_lang"] = args.translate_target_lang

    if args.workers:
        overrides.setdefault("queue", {})
        overrides["queue"]["worker_count"] = args.workers

    app = create_app(config_path=args.config, overrides=overrides or None)
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()
