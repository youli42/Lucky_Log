"""配置加载与校验。

读取项目根目录 config.json，缺失时生成默认模板。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pydantic

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "logs.db"

ALL_MODULES = [
    "system",
    "webservice",
    "docker",
    "cron",
    "ddns",
    "ssl",
    "webterminal",
    "rclone",
    "filebrowser",
    "wol",
    "ftpserver",
    "webdav",
    "dlnaservice",
    "frp",
    "cloudflared",
    "ipdb",
    "storagemanagement",
    "thirdPartyAuthManager",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "web": {"host": "0.0.0.0", "port": 8666},
    "collect_interval": 10,
    "cleanup": {"enabled": False, "days": 7},
    "instances": [
        {
            "name": "lucky-main",
            "host": "10.10.10.11",
            "port": "16601",
            "base": "/youlilucky",
            "token": "",
            "https": True,
            "enabled": True,
            "modules": [
                "system", "webservice", "docker", "cron", "ddns", "ssl",
                "webterminal", "rclone", "filebrowser", "wol",
            ],
        }
    ],
}


class InstanceConfig(pydantic.BaseModel):
    name: str
    host: str
    port: str
    base: str = "/youlilucky"
    token: str
    https: bool = True
    enabled: bool = True
    modules: list[str] = pydantic.Field(default_factory=lambda: ALL_MODULES.copy())

    @property
    def scheme(self) -> str:
        return "https" if self.https else "http"

    @property
    def base_url(self) -> str:
        base = self.base
        if not base.startswith("/"):
            base = "/" + base
        return f"{self.scheme}://{self.host}:{self.port}{base}"

    def api_url(self, path: str) -> str:
        path = path if path.startswith("/") else "/" + path
        if path.startswith("/api"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/api{path}"


class CleanupConfig(pydantic.BaseModel):
    enabled: bool = False
    days: int = 7


class WebConfig(pydantic.BaseModel):
    host: str = "0.0.0.0"
    port: int = 8666


class AppConfig(pydantic.BaseModel):
    web: WebConfig = pydantic.Field(default_factory=WebConfig)
    collect_interval: int = 10
    cleanup: CleanupConfig = pydantic.Field(default_factory=CleanupConfig)
    instances: list[InstanceConfig] = pydantic.Field(default_factory=list)

    def enabled_instances(self) -> list[InstanceConfig]:
        return [i for i in self.instances if i.enabled]


def load_config(path: Path | str | None = None) -> AppConfig:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.exists():
        cfg_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        data = copy.deepcopy(DEFAULT_CONFIG)
    else:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)
