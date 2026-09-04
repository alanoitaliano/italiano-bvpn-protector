from __future__ import annotations

import asyncio
import logging

from berconpy import ArmaClient, LoginRefused, Player, RCONCommandError, RCONError

from . import _berconpy_patches  # noqa: F401 - import for its patching side effect
from .config import LiveSettings, ServerConfig
from .discord_notify import DiscordNotifier
from .ip_lists import CUSTOM_LABEL, OOONINJA_LABEL, BlacklistHolder

_UNKNOWN_GUID = "unknown"

_RECONNECT_BACKOFF_START = 5.0
_RECONNECT_BACKOFF_MAX = 60.0

_GUID_WAIT_SECONDS = 1.0

_LABEL_DISPLAY_ORDER = ["Datacenter", "VPN", OOONINJA_LABEL, CUSTOM_LABEL]


def _ordered_counts(counts: dict[str, int]) -> list[tuple[str, int]]:
    ordered = [
        (label, counts[label]) for label in _LABEL_DISPLAY_ORDER if label in counts
    ]
    remaining = sorted(label for label in counts if label not in _LABEL_DISPLAY_ORDER)
    ordered.extend((label, counts[label]) for label in remaining)
    return ordered


def _is_real_guid(guid: str) -> bool:
    """BE reports an empty/all-zero GUID while it's still being computed."""
    return bool(guid) and any(c != "0" for c in guid)


def _mask_ip(ip: str) -> str:
    """Mask only the third (middle) octet, e.g. 192.168.42.7 -> 192.168.xxx.7."""
    parts = ip.split(".")
    if len(parts) != 4:
        return ip
    return f"{parts[0]}.{parts[1]}.xxx.{parts[3]}"


def _player_ip(player: Player) -> str:
    return player.addr.rsplit(":", 1)[0]


class ServerWorker:
    """Connects to one DayZ server over BattlEye RCON (via berconpy's ArmaClient)
    and kicks any player whose IP matches the shared blacklist."""

    def __init__(
        self,
        server_cfg: ServerConfig,
        blacklist_holder: BlacklistHolder,
        live: LiveSettings,
        logger: logging.Logger,
    ) -> None:
        self._cfg = server_cfg
        self._blacklist = blacklist_holder
        self._live = live
        self._log = logger
        self._notifier = DiscordNotifier(
            server_cfg.discord_webhook_url, server_cfg.name
        )
        self._client: ArmaClient | None = None
        self._kick_notified: set[int] = set()
        self._logged_joins: set[int] = set()
        self._guid_logged: set[int] = set()
        self._stopping = False

        self._command_lock = asyncio.Lock()

    def stop(self) -> None:
        """Marks this worker as intentionally shutting down."""
        self._stopping = True

    async def run(self) -> None:
        backoff = _RECONNECT_BACKOFF_START
        try:
            while not self._stopping:
                try:
                    await self._connect_and_monitor()
                    backoff = _RECONNECT_BACKOFF_START
                except asyncio.CancelledError:
                    if self._stopping:
                        raise
                    self._log.error("RCON session ended unexpectedly, reconnecting")
                except LoginRefused as exc:
                    self._log.error("RCON login refused (wrong password?): %s", exc)
                    await self._notifier.send(
                        f"⚠️ {self._cfg.name} - RCON login refused",
                        str(exc),
                        level="error",
                    )
                except RCONError as exc:
                    self._log.error("RCON error: %s", exc)
                    await self._notifier.send(
                        f"⚠️ {self._cfg.name} - RCON error", str(exc), level="error"
                    )
                except Exception:
                    self._log.exception("Unexpected error in server worker")

                if self._stopping:
                    break
                self._log.info("Reconnecting in %.0fs...", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX)
        finally:
            await self._notifier.close()

    async def _connect_and_monitor(self) -> None:
        self._kick_notified = set()
        self._logged_joins = set()
        self._guid_logged = set()

        client = ArmaClient()
        self._client = client
        client.dispatch.on_login(self._on_login)
        client.dispatch.on_player_connect(self._on_player_connect)
        client.dispatch.on_player_guid(self._on_player_guid_update)
        client.dispatch.on_player_verify_guid(self._on_player_guid_update)

        try:
            async with client.connect(
                self._cfg.host, self._cfg.rcon_port, self._cfg.rcon_password
            ):
                poll_task = asyncio.create_task(self._poll_loop())
                try:
                    await asyncio.Event().wait()
                finally:
                    poll_task.cancel()
        finally:
            self._client = None

    async def _on_login(self) -> None:
        self._log.info(
            "Connected to %s (%s:%d)%s",
            self._cfg.name,
            self._cfg.host,
            self._cfg.rcon_port,
            " [DEBUG MODE: no kicks will be issued]" if self._live.debug_mode else "",
        )

        counts = self._blacklist.counts_by_label()
        ordered = _ordered_counts(counts)
        total = sum(counts.values())
        self._log.info(
            "Blacklist loaded: %s (total=%d)",
            ", ".join(f"{label}={count}" for label, count in ordered),
            total,
        )

        fields = []
        if self._live.debug_mode:
            fields.append(
                {
                    "name": "Mode",
                    "value": "🧪 DEBUG - blocked IPs will be detected and logged, not kicked",
                    "inline": False,
                }
            )
        for label, count in ordered:
            fields.append(
                {
                    "name": label,
                    "value": f"{count:,} IP ranges blocked",
                    "inline": False,
                }
            )
        fields.append(
            {"name": "Total", "value": f"{total:,} IP ranges blocked", "inline": False}
        )

        await self._notifier.send(
            f"✅ {self._cfg.name} - connected",
            "RCON connection established.",
            level="success",
            fields=fields,
        )
        await self._scan_players(already_connected=True)

    async def _poll_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._cfg.poll_interval_seconds)
                await self._scan_players(already_connected=False)
        except asyncio.CancelledError:
            pass

    async def _scan_players(self, already_connected: bool) -> None:
        assert self._client is not None
        try:
            async with self._command_lock:
                players = await self._client.fetch_players()
        except RCONCommandError as exc:
            self._log.warning("Fetching players failed: %s", exc)
            return
        if already_connected:
            self._log.info("Initial scan: %d player(s) connected", len(players))
        for player in players:
            await self._check_and_kick_player(
                player, already_connected=already_connected
            )

    async def _on_player_connect(self, player: Player) -> None:
        self._log.info(
            "Raw BE connect message: Player #%d %s (%s) connected",
            player.id,
            player.name,
            player.addr,
        )
        await self._check_and_kick_player(player, already_connected=False)

    async def _on_player_guid_update(self, player: Player) -> None:
        if not _is_real_guid(player.guid) or player.id in self._guid_logged:
            return
        self._guid_logged.add(player.id)
        self._log.info(
            "GUID resolved for %s (%s): %s",
            player.name,
            _player_ip(player),
            player.guid,
        )

    async def _check_and_kick_player(
        self, player: Player, already_connected: bool
    ) -> None:
        ip = _player_ip(player)

        is_new_join = player.id not in self._logged_joins
        self._logged_joins.add(player.id)

        kicked = False
        matched = False
        whitelisted = False
        label: str | None = None
        reason: str | None = None
        guid_waited = False
        if self._client is not None:
            label = self._blacklist.check(ip)
            if label is not None:
                matched = True

                if not _is_real_guid(player.guid):
                    await asyncio.sleep(_GUID_WAIT_SECONDS)
                guid_waited = True

                if player.guid and player.guid.lower() in self._live.whitelisted_guids:
                    whitelisted = True
                else:
                    reason = (
                        self._live.custom_kick_message
                        if label == CUSTOM_LABEL
                        else self._live.kick_message
                    )
                    if not self._live.debug_mode:
                        try:
                            async with self._command_lock:
                                await self._client.kick(player.id, reason)
                            kicked = True
                        except RCONCommandError as exc:
                            self._log.error(
                                "Failed to kick player %s (%s): %s",
                                player.name,
                                ip,
                                exc,
                            )

        if not guid_waited and not _is_real_guid(player.guid):
            await asyncio.sleep(_GUID_WAIT_SECONDS)
        guid = player.guid or _UNKNOWN_GUID

        if is_new_join:
            verb = "Player already connected" if already_connected else "Player joined"
            if kicked:
                kicked_desc = f"yes ({label})"
            elif whitelisted:
                kicked_desc = f"no - whitelisted GUID (matched {label})"
            elif matched and self._live.debug_mode:
                kicked_desc = f"no - DEBUG would kick ({label})"
            else:
                kicked_desc = "no"
            self._log.info(
                "%s: %s | IP: %s | GUID: %s | Kicked: %s",
                verb,
                player.name,
                ip,
                guid,
                kicked_desc,
            )

        should_report = kicked or (matched and self._live.debug_mode)
        already_notified = player.id in self._kick_notified
        if should_report or whitelisted:
            self._kick_notified.add(player.id)

        if whitelisted and not already_notified:
            self._log.info(
                "Allowed player %s (%s) [GUID: %s] - matched %s list but GUID is whitelisted",
                player.name,
                ip,
                guid,
                label,
            )

        if should_report and not already_notified:
            debug_prefix = "[DEBUG] Would kick" if self._live.debug_mode else "Kicked"
            self._log.info(
                "%s player %s (%s) [GUID: %s] - matched %s list. Reason: %s",
                debug_prefix,
                player.name,
                ip,
                guid,
                label,
                reason,
            )
            discord_title_prefix = (
                "🧪 [DEBUG] would kick" if self._live.debug_mode else "🚫 player kicked"
            )
            if self._live.mask_ip_in_discord:
                ip_field_value = f"`{_mask_ip(ip)}`"
            else:
                ip_field_value = f"[{ip}](https://whatismyipaddress.com/ip/{ip})"
            fields = [
                {"name": "Player", "value": player.name or "Unknown", "inline": False},
                {"name": "IP", "value": ip_field_value, "inline": False},
                {"name": "GUID", "value": f"`{guid}`", "inline": False},
                {"name": "Matched List", "value": label, "inline": False},
                {"name": "Reason", "value": reason, "inline": False},
            ]
            await self._notifier.send(
                f"{discord_title_prefix} - {self._cfg.name}",
                level="kick",
                fields=fields,
            )
