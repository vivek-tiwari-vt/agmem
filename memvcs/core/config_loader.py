"""
agmem config loader - user and repo config with safe credential handling.

Loads config from ~/.config/agmem/config.yaml and optionally repo .agmemrc or
.mem/config.yaml. Credentials are never stored in config; only env var names
and non-secret options. Use os.getenv() to resolve secrets.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Default env var names for S3 (config may override with different var names)
DEFAULT_S3_ACCESS_KEY_VAR = "AWS_ACCESS_KEY_ID"
DEFAULT_S3_SECRET_KEY_VAR = "AWS_SECRET_ACCESS_KEY"

# Canonical config keys
CONFIG_CLOUD = "cloud"
CONFIG_CLOUD_S3 = "s3"
CONFIG_CLOUD_GCS = "gcs"
CONFIG_PII = "pii"


def _user_config_path() -> Path:
    """Path to user-level config (XDG or ~/.config/agmem/config.yaml)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "agmem" / "config.yaml"
    return Path.home() / ".config" / "agmem" / "config.yaml"


def _repo_config_paths(repo_root: Path) -> List[Path]:
    """Paths to repo-level config (first existing wins)."""
    root = Path(repo_root).resolve()
    return [
        root / ".agmemrc",
        root / ".mem" / "config.yaml",
    ]


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file with safe_load. Returns {} on missing file or error."""
    if not path.exists() or not path.is_file():
        return {}
    if not YAML_AVAILABLE:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge override into base recursively. Override wins; base is not mutated."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_gcs_credentials_path(
    raw_path: Optional[str],
    repo_root: Optional[Path],
) -> Optional[str]:
    """
    Resolve GCS credentials_path to absolute and ensure under allowed root.
    Allowed: repo_root (if given) or user home. Returns None if invalid or missing.
    """
    if not raw_path or not raw_path.strip():
        return None
    path = Path(raw_path.strip()).expanduser()
    if not path.is_absolute():
        base = Path(repo_root).resolve() if repo_root else Path.home()
        path = (base / path).resolve()
    else:
        path = path.resolve()
    if not path.exists() or not path.is_file():
        return None
    allowed_bases: List[Path] = []
    if repo_root:
        allowed_bases.append(Path(repo_root).resolve())
    allowed_bases.append(Path.home())
    for base in allowed_bases:
        try:
            path.resolve().relative_to(base)
            return str(path)
        except ValueError:
            continue
    return None


def _apply_gcs_credentials_path(config: Dict[str, Any], repo_root: Optional[Path]) -> None:
    """Resolve and validate cloud.gcs.credentials_path in-place; remove if invalid."""
    gcs = config.get(CONFIG_CLOUD, {}).get(CONFIG_CLOUD_GCS)
    if not isinstance(gcs, dict) or not gcs.get("credentials_path"):
        return
    raw_path = gcs.get("credentials_path")
    resolved = _resolve_gcs_credentials_path(raw_path, repo_root)
    if CONFIG_CLOUD not in config:
        config[CONFIG_CLOUD] = {}
    if CONFIG_CLOUD_GCS not in config[CONFIG_CLOUD]:
        config[CONFIG_CLOUD][CONFIG_CLOUD_GCS] = dict(gcs)
    if resolved:
        config[CONFIG_CLOUD][CONFIG_CLOUD_GCS]["credentials_path"] = resolved
    else:
        config[CONFIG_CLOUD][CONFIG_CLOUD_GCS] = {
            k: v
            for k, v in config[CONFIG_CLOUD][CONFIG_CLOUD_GCS].items()
            if k != "credentials_path"
        }


def load_agmem_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load merged agmem config (user + optional repo). No secrets in config.

    User config: ~/.config/agmem/config.yaml (or XDG_CONFIG_HOME/agmem/config.yaml).
    Repo config: repo_root/.agmemrc or repo_root/.mem/config.yaml (first found).
    Merge order: defaults -> user -> repo (repo overrides user).

    For cloud.gcs.credentials_path: resolved to absolute and validated under
    repo root or user home.

    Returns:
        Merged config dict. Use getattr-style access for optional nested keys.
    """
    config = {}
    user_path = _user_config_path()
    user_cfg = _load_yaml(user_path)
    if user_cfg:
        config = _deep_merge(config, user_cfg)

    if repo_root:
        for p in _repo_config_paths(repo_root):
            repo_cfg = _load_yaml(p)
            if repo_cfg:
                config = _deep_merge(config, repo_cfg)
                break

    _apply_gcs_credentials_path(config, repo_root)
    return config


def _get_cloud_section(config: Optional[Dict[str, Any]], section: str) -> Optional[Dict[str, Any]]:
    """Return cloud.section dict if present and dict, else None."""
    if not config:
        return None
    cloud = config.get(CONFIG_CLOUD, {})
    if not isinstance(cloud, dict):
        return None
    val = cloud.get(section)
    return val if isinstance(val, dict) else None


def get_s3_options_from_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build S3 constructor kwargs from config. Resolves credentials from env only.

    Returns dict with keys: region, endpoint_url, access_key, secret_key (and
    optionally lock_table). access_key/secret_key are set only from os.getenv(...).
    """
    out: Dict[str, Any] = {}
    s3 = _get_cloud_section(config, CONFIG_CLOUD_S3)
    if not s3:
        return out
    if s3.get("region"):
        out["region"] = s3["region"]
    if s3.get("endpoint_url"):
        out["endpoint_url"] = s3["endpoint_url"]
    if s3.get("lock_table"):
        out["lock_table"] = s3["lock_table"]
    access_var = s3.get("access_key_var") or DEFAULT_S3_ACCESS_KEY_VAR
    secret_var = s3.get("secret_key_var") or DEFAULT_S3_SECRET_KEY_VAR
    access = os.getenv(access_var)
    secret = os.getenv(secret_var)
    if access and secret:
        out["access_key"] = access
        out["secret_key"] = secret
    return out


def get_gcs_options_from_config(
    config: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build GCS constructor kwargs from config. Credentials from env or validated path.

    Returns dict with keys: project, credentials_path, or credentials_info (dict
    from JSON string in env). Caller (GCS adapter) uses credentials_path or
    credentials_info; never raw secret values in config.
    """
    out: Dict[str, Any] = {}
    gcs = _get_cloud_section(config, CONFIG_CLOUD_GCS)
    if not gcs:
        return out
    if gcs.get("project"):
        out["project"] = gcs["project"]
    if gcs.get("credentials_path"):
        out["credentials_path"] = gcs["credentials_path"]
    if gcs.get("credentials_json_var"):
        json_str = os.getenv(gcs["credentials_json_var"])
        if json_str:
            try:
                out["credentials_info"] = json.loads(json_str)
            except (ValueError, TypeError):
                pass
    return out


def _get_pii_section(config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return pii section dict if present and dict, else None."""
    if not config:
        return None
    pii = config.get(CONFIG_PII)
    return pii if isinstance(pii, dict) else None


def pii_enabled(config: Optional[Dict[str, Any]]) -> bool:
    """Return True if PII scanning is enabled (default True when key missing)."""
    pii = _get_pii_section(config)
    if not pii or "enabled" not in pii:
        return True
    return bool(pii["enabled"])


def pii_allowlist(config: Optional[Dict[str, Any]]) -> List[str]:
    """Return list of path globs to skip for PII scanning."""
    pii = _get_pii_section(config)
    if not pii:
        return []
    allow = pii.get("allowlist")
    if not isinstance(allow, list):
        return []
    return [str(x) for x in allow]
