from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .config import (
    AppConfig,
    ConfigError,
    LiveSettings,
    apply_live_update,
    load_config,
    unsupported_live_changes,
)
from .ip_lists import BlacklistHolder, build_blacklist

logger = logging.getLogger("live_config")


async def periodic_config_reloader(
    config_path: Path,
    live: LiveSettings,
    blacklist_holder: BlacklistHolder,
    reference_config: AppConfig,
    interval_seconds: float,
) -> None:
    """Periodically re-reads config_path and hot-applies whatever's safe to change
    without restarting: kick_message, custom_kick_message, debug_mode,
    mask_ip_in_discord, custom_blocked_ips, whitelisted_guids.
    """
    interval_seconds = max(interval_seconds, 1.0)
    while True:
        await asyncio.sleep(interval_seconds)

        if not config_path.exists():
            logger.warning(
                "Config file missing at reload check; keeping current settings"
            )
            continue
        try:
            new_config = load_config(config_path)
        except ConfigError as exc:
            logger.warning("Config reload failed, keeping current settings: %s", exc)
            continue
        except Exception:
            logger.exception(
                "Unexpected error reloading config, keeping current settings"
            )
            continue

        changes = apply_live_update(live, new_config)
        for change in changes:
            logger.info("Config reloaded: %s", change)

        unsupported = unsupported_live_changes(reference_config, new_config)
        if unsupported:
            logger.warning(
                "Config changes to %s were detected but need a restart to take effect",
                ", ".join(unsupported),
            )

        if any(change.startswith("custom_blocked_ips") for change in changes):
            logger.info("custom_blocked_ips changed - rebuilding blacklist now")
            try:
                blacklist_holder.blacklist = await build_blacklist(
                    reference_config.ip_lists, live.custom_blocked_ips
                )
            except Exception:
                logger.exception("Failed to rebuild blacklist after config reload")
