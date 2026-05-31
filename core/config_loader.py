"""配置加载器 - 从 YAML 读取配置"""
import yaml
import os
from pathlib import Path
from typing import Any, Optional

_config_cache: Optional[dict] = None
_config_path: Optional[str] = None


def load_config(config_path: str = None) -> dict:
    """加载配置文件，支持缓存"""
    global _config_cache, _config_path
    if _config_cache and config_path is None:
        return _config_cache

    if config_path is None:
        # 默认路径：项目根目录/config/config.yaml
        project_root = Path(__file__).parent.parent
        config_path = str(project_root / "config" / "config.yaml")

    _config_path = config_path
    with open(config_path, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f)
    return _config_cache


def get_config(key_path: str, default: Any = None) -> Any:
    """用点号路径获取配置值，如 'personality.name'"""
    cfg = load_config()
    keys = key_path.split(".")
    val = cfg
    for k in keys:
        if isinstance(val, dict):
            val = val.get(k, default)
        else:
            return default
    return val


def reload_config():
    """强制重新加载配置"""
    global _config_cache
    _config_cache = None
    return load_config(_config_path)
