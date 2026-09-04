from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from . import blacklist_db
from .config import IPListsConfig, LiveSettings

logger = logging.getLogger("ip_lists")

_HTTP_TIMEOUT = httpx.Timeout(30.0)

CUSTOM_LABEL = "Custom"
OOONINJA_LABEL = "Residential VPN" # Best effort list


@dataclass(slots=True)
class _Interval:
    start: int
    end: int
    label: str


class IPBlacklist:
    """Sorted, mergeable set of blocked IPv4 ranges with a source label each."""

    def __init__(self, intervals: list[_Interval]):
        self._intervals = sorted(intervals, key=lambda i: i.start)

    def __len__(self) -> int:
        return len(self._intervals)

    def check(self, ip_str: str) -> str | None:
        """Return the matching list label (e.g. 'Datacenter') or None."""
        try:
            ip_int = int(ipaddress.IPv4Address(ip_str))
        except ipaddress.AddressValueError:
            return None
        for interval in self._intervals:
            if interval.start > ip_int:
                break
            if interval.start <= ip_int <= interval.end:
                return interval.label
        return None

    def counts_by_label(self) -> dict[str, int]:
        """Number of blocked ranges per source label, e.g. {'Datacenter': 42849}."""
        counts: dict[str, int] = {}
        for interval in self._intervals:
            counts[interval.label] = counts.get(interval.label, 0) + 1
        return counts


def _parse_cidr_lines(lines: list[str], label: str) -> list[_Interval]:
    """Parse one IPv4 address/CIDR per line. Trailing '# comment' text (e.g. a
    provider tag) is stripped, and lines that are entirely a comment are skipped."""
    intervals: list[_Interval] = []
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            network = ipaddress.IPv4Network(line, strict=False)
        except ValueError:
            logger.debug("Skipping unparseable line in %s list: %r", label, line)
            continue
        intervals.append(
            _Interval(
                start=int(network.network_address),
                end=int(network.broadcast_address),
                label=label,
            )
        )
    return intervals


def _db_path(cache_dir: Path) -> Path:
    return cache_dir / "blacklist_cache.db"


async def _fetch_source(
    client: httpx.AsyncClient, url: str, label: str, db_path: Path
) -> list[_Interval]:
    """Fetch and parse one source, persisting the parsed ranges to SQLite. On
    failure, falls back to whatever was stored there from the last successful fetch."""
    try:
        response = await client.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        intervals = _parse_cidr_lines(response.text.splitlines(), label)
        await asyncio.to_thread(
            blacklist_db.replace_source,
            db_path,
            label,
            [(i.start, i.end) for i in intervals],
        )
        logger.info("Fetched %s list from %s (%d ranges)", label, url, len(intervals))
        return intervals
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Failed to fetch %s list from %s: %s", label, url, exc)
        cached_ranges = await asyncio.to_thread(blacklist_db.load_source, db_path, label)
        if cached_ranges:
            logger.warning(
                "Falling back to %d cached %s range(s) from SQLite", len(cached_ranges), label
            )
            return [_Interval(start=s, end=e, label=label) for s, e in cached_ranges]
        logger.error("No cached %s ranges available; this list will be empty", label)
        return []


async def build_blacklist(
    config: IPListsConfig, custom_ips: list[str] | None = None
) -> IPBlacklist:
    db_path = _db_path(config.cache_dir)
    async with httpx.AsyncClient() as client:
        fetches = [
            _fetch_source(client, config.datacenter_url, "Datacenter", db_path),
            _fetch_source(client, config.vpn_url, "VPN", db_path),
        ]
        if config.oooninja_enabled:
            fetches.append(_fetch_source(client, config.oooninja_url, OOONINJA_LABEL, db_path))
        results = await asyncio.gather(*fetches)

    dc_intervals, vpn_intervals = results[0], results[1]
    oooninja_intervals = results[2] if config.oooninja_enabled else []
    custom_intervals = _parse_cidr_lines(custom_ips or [], CUSTOM_LABEL)

    blacklist = IPBlacklist(dc_intervals + vpn_intervals + oooninja_intervals + custom_intervals)
    logger.info(
        "Blacklist rebuilt: %d ranges (datacenter=%d, vpn=%d, residential-vpn=%d, custom=%d)",
        len(blacklist),
        len(dc_intervals),
        len(vpn_intervals),
        len(oooninja_intervals),
        len(custom_intervals),
    )
    return blacklist


class BlacklistHolder:
    """Mutable holder so server workers always see the latest blacklist without restarting."""

    def __init__(self) -> None:
        self.blacklist = IPBlacklist([])

    def check(self, ip_str: str) -> str | None:
        return self.blacklist.check(ip_str)

    def counts_by_label(self) -> dict[str, int]:
        return self.blacklist.counts_by_label()


async def periodic_updater(config: IPListsConfig, holder: BlacklistHolder, live: LiveSettings) -> None:
    interval_seconds = max(config.update_interval_hours, 0.1) * 3600
    while True:
        try:
            holder.blacklist = await build_blacklist(config, live.custom_blocked_ips)
        except Exception:
            logger.exception("Unexpected error while rebuilding IP blacklist")
        await asyncio.sleep(interval_seconds)
