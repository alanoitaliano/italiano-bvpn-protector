from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ConfigError,
    build_live_settings,
    load_config,
)
from .ip_lists import BlacklistHolder, build_blacklist, periodic_updater
from .live_config import periodic_config_reloader
from .logging_setup import get_server_logger, setup_root_logging
from .server_worker import ServerWorker
from .singleton import AlreadyRunningError, acquire_singleton_lock

logger = logging.getLogger("app")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DayZ BattlEye VPN/Datacenter IP kicker"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON (default: {DEFAULT_CONFIG_PATH})",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    lock_path = args.config.with_suffix(".lock")
    try:
        _lock_handle = acquire_singleton_lock(lock_path)
    except AlreadyRunningError as exc:
        print(
            f"{exc}\nKill the other instance before starting a new one.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    try:
        config: AppConfig = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        raise SystemExit(1) from exc

    setup_root_logging(config.log_dir)
    logger.info("Starting with %d server(s) configured", len(config.servers))
    if config.debug_mode:
        logger.warning(
            "[DEBUG MODE] Blocked IPs will be detected and logged/notified, but NOT kicked."
        )

    holder = BlacklistHolder()
    logger.info("Building initial IP blacklist (datacenter + VPN + custom)...")
    holder.blacklist = await build_blacklist(config.ip_lists, config.custom_blocked_ips)

    live = build_live_settings(config)
    logger.info(
        "Config hot-reload enabled (every %.0fs): kick messages, debug_mode, "
        "mask_ip_in_discord, custom_blocked_ips, whitelisted_guids. Restart is still "
        "needed for server/RCON/ip_lists/log_dir changes.",
        config.config_reload_interval_seconds,
    )

    tasks: list[asyncio.Task] = [
        asyncio.create_task(periodic_updater(config.ip_lists, holder, live)),
        asyncio.create_task(
            periodic_config_reloader(
                args.config, live, holder, config, config.config_reload_interval_seconds
            )
        ),
    ]
    workers: list[ServerWorker] = []

    for server_cfg in config.servers:
        server_logger = get_server_logger(config.log_dir, server_cfg.name)
        worker = ServerWorker(server_cfg, holder, live, server_logger)
        workers.append(worker)
        tasks.append(asyncio.create_task(worker.run()))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await stop_event.wait()
    logger.info("Shutting down...")

    for worker in workers:
        worker.stop()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
