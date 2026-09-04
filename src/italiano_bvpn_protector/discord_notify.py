from __future__ import annotations

import asyncio
import logging

import httpx

from ._version import APP_VERSION

logger = logging.getLogger("discord")

_COLORS = {
    "info": 0x3498DB,
    "success": 0x2ECC71,
    "warning": 0xF1C40F,
    "error": 0xE74C3C,
    "kick": 0xE74C3C,
}

_FOOTER_TEXT = f"Italiano Better VPN Protector v{APP_VERSION} - https://github.com/alanoitaliano/italiano-bvpn-protector"


class DiscordNotifier:
    def __init__(self, webhook_url: str | None, server_name: str):
        self._webhook_url = webhook_url
        self._server_name = server_name
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def send(
        self,
        title: str,
        description: str = "",
        level: str = "info",
        fields: list[dict] | None = None,
    ) -> None:
        if not self._webhook_url:
            return
        embed: dict = {
            "title": title,
            "color": _COLORS.get(level, _COLORS["info"]),
            "footer": {"text": _FOOTER_TEXT},
        }
        if description:
            embed["description"] = description
        if fields:
            embed["fields"] = fields
        payload = {"embeds": [embed]}
        for attempt in range(3):
            try:
                response = await self._client.post(self._webhook_url, json=payload)
                if response.status_code == 429:
                    retry_after = float(response.json().get("retry_after", 1.0))
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return
            except httpx.HTTPError as exc:
                logger.warning(
                    "Discord webhook post failed (attempt %d): %s", attempt + 1, exc
                )
                await asyncio.sleep(1.5 * (attempt + 1))
        logger.error(
            "Giving up sending Discord notification for %s: %s",
            self._server_name,
            title,
        )
