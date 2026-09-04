from __future__ import annotations

import ipaddress
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("./data/config.json")

DEFAULT_DATACENTER_URL = (
    "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv4.txt"
)
DEFAULT_VPN_URL = (
    "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt"
)
DEFAULT_OOONINJA_URL = "https://az0-vpnip-public.oooninja.com/ip.txt"
DEFAULT_KICK_MESSAGE = "Datacenter/VPN IP detected"
DEFAULT_CUSTOM_KICK_MESSAGE = "Blocked IP address"

EXAMPLE_CONFIG = {
    "servers": [
        {
            "name": "MyDayZServer",
            "host": "127.0.0.1",
            "rcon_port": 2302,
            "rcon_password": "changeme",
            "discord_webhook_url": "https://discord.com/api/webhooks/xxxxxxxxxxxx/yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
            "poll_interval_seconds": 15,
        }
    ],
    "ip_lists": {
        "update_interval_hours": 12,
        "datacenter_url": DEFAULT_DATACENTER_URL,
        "vpn_url": DEFAULT_VPN_URL,
        "oooninja_enabled": True,
        "oooninja_url": DEFAULT_OOONINJA_URL,
        "cache_dir": "./data/lists",
    },
    "custom_blocked_ips": [
        "203.0.113.5",
        "198.51.100.0/24",
    ],
    "whitelisted_guids": [
        "c779d3141c0adcb906e45948212c5b3f",
    ],
    "kick_message": DEFAULT_KICK_MESSAGE,
    "custom_kick_message": DEFAULT_CUSTOM_KICK_MESSAGE,
    "debug_mode": True,
    "mask_ip_in_discord": True,
    "config_reload_interval_seconds": 30,
    "log_dir": "./data/logs",
}


class ConfigError(Exception):
    pass


@dataclass(slots=True)
class ServerConfig:
    name: str
    host: str
    rcon_port: int
    rcon_password: str
    discord_webhook_url: str | None = None
    poll_interval_seconds: int = 15


@dataclass(slots=True)
class IPListsConfig:
    update_interval_hours: float = 12.0
    datacenter_url: str = DEFAULT_DATACENTER_URL
    vpn_url: str = DEFAULT_VPN_URL
    oooninja_enabled: bool = True
    oooninja_url: str = DEFAULT_OOONINJA_URL
    cache_dir: Path = Path("./data/lists")


@dataclass(slots=True)
class AppConfig:
    servers: list[ServerConfig] = field(default_factory=list)
    ip_lists: IPListsConfig = field(default_factory=IPListsConfig)
    custom_blocked_ips: list[str] = field(default_factory=list)
    whitelisted_guids: list[str] = field(default_factory=list)
    kick_message: str = DEFAULT_KICK_MESSAGE
    custom_kick_message: str = DEFAULT_CUSTOM_KICK_MESSAGE
    debug_mode: bool = False
    mask_ip_in_discord: bool = True
    config_reload_interval_seconds: float = 30.0
    log_dir: Path = Path("./data/logs")


@dataclass(slots=True)
class LiveSettings:
    """The subset of config that hot-reloads without restarting: no server
    connection details, IP list sources, or log_dir - those still need a restart.
    Server workers hold a reference to one shared instance of this."""

    kick_message: str
    custom_kick_message: str
    custom_blocked_ips: list[str]
    whitelisted_guids: set[str]
    debug_mode: bool
    mask_ip_in_discord: bool


def build_live_settings(config: AppConfig) -> LiveSettings:
    return LiveSettings(
        kick_message=config.kick_message,
        custom_kick_message=config.custom_kick_message,
        custom_blocked_ips=list(config.custom_blocked_ips),
        whitelisted_guids={g.lower() for g in config.whitelisted_guids},
        debug_mode=config.debug_mode,
        mask_ip_in_discord=config.mask_ip_in_discord,
    )


def apply_live_update(live: LiveSettings, new_config: AppConfig) -> list[str]:
    """Mutates `live` in place to match new_config's hot-reloadable fields.
    Returns a human-readable description of each field that actually changed."""
    changes: list[str] = []

    if live.kick_message != new_config.kick_message:
        changes.append(f"kick_message: {live.kick_message!r} -> {new_config.kick_message!r}")
        live.kick_message = new_config.kick_message

    if live.custom_kick_message != new_config.custom_kick_message:
        changes.append(
            f"custom_kick_message: {live.custom_kick_message!r} -> "
            f"{new_config.custom_kick_message!r}"
        )
        live.custom_kick_message = new_config.custom_kick_message

    if live.debug_mode != new_config.debug_mode:
        changes.append(f"debug_mode: {live.debug_mode} -> {new_config.debug_mode}")
        live.debug_mode = new_config.debug_mode

    if live.mask_ip_in_discord != new_config.mask_ip_in_discord:
        changes.append(
            f"mask_ip_in_discord: {live.mask_ip_in_discord} -> {new_config.mask_ip_in_discord}"
        )
        live.mask_ip_in_discord = new_config.mask_ip_in_discord

    new_custom_ips = list(new_config.custom_blocked_ips)
    if live.custom_blocked_ips != new_custom_ips:
        changes.append(
            f"custom_blocked_ips: {len(live.custom_blocked_ips)} -> {len(new_custom_ips)} entries"
        )
        live.custom_blocked_ips = new_custom_ips

    new_guids = {g.lower() for g in new_config.whitelisted_guids}
    if live.whitelisted_guids != new_guids:
        added = len(new_guids - live.whitelisted_guids)
        removed = len(live.whitelisted_guids - new_guids)
        changes.append(f"whitelisted_guids: +{added} -{removed} (now {len(new_guids)} total)")
        live.whitelisted_guids = new_guids

    return changes


def unsupported_live_changes(old: AppConfig, new: AppConfig) -> list[str]:
    """Config fields that changed but require a restart to take effect."""
    changes: list[str] = []

    def _server_signature(cfg: ServerConfig) -> tuple:
        return (
            cfg.name,
            cfg.host,
            cfg.rcon_port,
            cfg.rcon_password,
            cfg.discord_webhook_url,
            cfg.poll_interval_seconds,
        )

    if [_server_signature(s) for s in old.servers] != [_server_signature(s) for s in new.servers]:
        changes.append("servers")
    if old.ip_lists != new.ip_lists:
        changes.append("ip_lists")
    if old.log_dir != new.log_dir:
        changes.append("log_dir")
    return changes


def _require(mapping: dict, key: str, ctx: str) -> object:
    if key not in mapping:
        raise ConfigError(f"Missing required field '{key}' in {ctx}")
    return mapping[key]


def _parse_server(raw: dict, index: int) -> ServerConfig:
    ctx = f"servers[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{ctx} must be an object")
    return ServerConfig(
        name=str(_require(raw, "name", ctx)),
        host=str(_require(raw, "host", ctx)),
        rcon_port=int(_require(raw, "rcon_port", ctx)),
        rcon_password=str(_require(raw, "rcon_password", ctx)),
        discord_webhook_url=raw.get("discord_webhook_url") or None,
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 15)),
    )


def _parse_ip_lists(raw: dict | None) -> IPListsConfig:
    raw = raw or {}
    return IPListsConfig(
        update_interval_hours=float(raw.get("update_interval_hours", 12.0)),
        datacenter_url=str(raw.get("datacenter_url", DEFAULT_DATACENTER_URL)),
        vpn_url=str(raw.get("vpn_url", DEFAULT_VPN_URL)),
        oooninja_enabled=bool(raw.get("oooninja_enabled", True)),
        oooninja_url=str(raw.get("oooninja_url", DEFAULT_OOONINJA_URL)),
        cache_dir=Path(raw.get("cache_dir", "./data/lists")),
    )


def _parse_custom_blocked_ips(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError(
            "'custom_blocked_ips' must be a list of IP addresses/CIDR ranges"
        )
    entries: list[str] = []
    for i, item in enumerate(raw):
        entry = str(item).strip()
        try:
            ipaddress.IPv4Network(entry, strict=False)
        except ValueError as exc:
            raise ConfigError(
                f"custom_blocked_ips[{i}] is not a valid IPv4 address/CIDR: {entry!r}"
            ) from exc
        entries.append(entry)
    return entries


def _parse_whitelisted_guids(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("'whitelisted_guids' must be a list of BattlEye GUID strings")
    return [str(g).strip().lower() for g in raw if str(g).strip()]


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
        print(
            f"No config found. Wrote an example config to {path}.\n"
            "Edit it with your server(s) RCON details and Discord webhook(s), then run again.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc

    servers_raw = _require(raw, "servers", "config")
    if not isinstance(servers_raw, list) or not servers_raw:
        raise ConfigError("'servers' must be a non-empty list")

    servers = [_parse_server(s, i) for i, s in enumerate(servers_raw)]
    names = [s.name for s in servers]
    if len(names) != len(set(names)):
        raise ConfigError("Server 'name' values must be unique")

    return AppConfig(
        servers=servers,
        ip_lists=_parse_ip_lists(raw.get("ip_lists")),
        custom_blocked_ips=_parse_custom_blocked_ips(raw.get("custom_blocked_ips")),
        whitelisted_guids=_parse_whitelisted_guids(raw.get("whitelisted_guids")),
        kick_message=str(raw.get("kick_message", DEFAULT_KICK_MESSAGE)),
        custom_kick_message=str(
            raw.get("custom_kick_message", DEFAULT_CUSTOM_KICK_MESSAGE)
        ),
        debug_mode=bool(raw.get("debug_mode", False)),
        mask_ip_in_discord=bool(raw.get("mask_ip_in_discord", True)),
        config_reload_interval_seconds=float(raw.get("config_reload_interval_seconds", 30.0)),
        log_dir=Path(raw.get("log_dir", "./data/logs")),
    )
