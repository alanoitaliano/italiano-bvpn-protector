# Italiano Better VPN Protector

Italiano Better VPN Protector automatically removes players connecting to a DayZ server from known VPN and datacenter IP addresses.

It connects through BattlEye RCon, checks players as they join, and can protect several DayZ servers from one installation. Optional Discord reports show connection status, errors, and kick details.

## Features

- Checks players immediately when they connect.
- Regularly rescans the player list as a backup.
- Blocks known datacenter, VPN, and residential VPN addresses.
- Supports your own blocked IP addresses and network ranges.
- Allows trusted players through with a BattlEye GUID whitelist.
- Provides a safe debug mode that reports matches without kicking.
- Sends optional Discord notifications.
- Stores separate logs for each DayZ server.
- Refreshes IP lists automatically and uses cached lists during provider outages.
- Reconnects automatically if the RCon connection drops.
- Reloads most protection settings without a restart.

IP-based detection is not perfect. Providers change addresses, some VPNs may not be listed, and legitimate players can occasionally be matched. Start in debug mode and review the results before enabling kicks.

## Before you start

You need:

- A DayZ server with BattlEye RCon enabled
- The BattlEye RCon host, port, and password
- Internet access for downloading IP lists
- Docker, or Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A Discord webhook only if you want Discord reports

Your game host's control panel may display the RCon details. The RCon port is not necessarily the same as the game or query port.

## Quick start with Docker

This is the simplest option for a machine that already runs Docker.

1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Create your working configuration:

Linux:

```bash
cp data/config.example.json data/config.json
```

Windows PowerShell:

```powershell
Copy-Item data/config.example.json data/config.json
```

4. Edit `data/config.json` with your RCon details.
5. Start the protector:

```text
docker compose up -d
```

6. Follow the startup output:

```text
docker compose logs -f
```

Press `Ctrl+C` to stop following the output. The protector continues running in the background.

Docker stores the configuration, cached IP lists, and logs in the local `data` folder. The container restarts automatically unless you stop it yourself.

### RCon address when using Docker

The `host` setting must be an address the container can reach. Do not use `127.0.0.1` for a DayZ server running outside the container, because that address points back to the container itself.

- For a DayZ server on another machine, use that machine's reachable IP address.
- With Docker Desktop, `host.docker.internal` can be used to reach a DayZ server on the Docker host.
- On a Linux server, use an address for the host that is reachable from Docker.

Make sure the firewall and hosting provider allow RCon connections from the machine running the protector.

### Updating the Docker installation

```text
docker compose pull
docker compose up -d
```

To stop and remove the container without deleting your configuration or logs:

```text
docker compose down
```

## Running without Docker

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run this inside the project folder:

```text
uv sync
```

Create `data/config.json` from the supplied example using one of the copy commands above, then edit it with your server details.

Start the protector:

```text
uv run italiano-bvpn-protector
```

When running directly on the same machine as the DayZ server, `127.0.0.1` is normally the correct RCon host.

To use a configuration stored elsewhere:

```text
uv run italiano-bvpn-protector --config /path/to/config.json
```

Keep the process running for protection to remain active. Stop it with `Ctrl+C`.

## Configuration

The supplied `data/config.example.json` contains every available setting:

```json
{
  "servers": [
    {
      "name": "MyDayZServer",
      "host": "127.0.0.1",
      "rcon_port": 2302,
      "rcon_password": "changeme",
      "discord_webhook_url": "",
      "poll_interval_seconds": 15
    }
  ],
  "ip_lists": {
    "update_interval_hours": 12,
    "datacenter_url": "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv4.txt",
    "vpn_url": "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt",
    "oooninja_enabled": true,
    "oooninja_url": "https://az0-vpnip-public.oooninja.com/ip.txt",
    "cache_dir": "./data/lists"
  },
  "custom_blocked_ips": [],
  "whitelisted_guids": [],
  "kick_message": "Datacenter/VPN IP detected",
  "custom_kick_message": "Blocked IP address",
  "debug_mode": true,
  "mask_ip_in_discord": true,
  "config_reload_interval_seconds": 30,
  "log_dir": "./data/logs"
}
```

### Server settings

| Setting | Description |
| --- | --- |
| `name` | A unique name used in logs and Discord reports. |
| `host` | The hostname or IP address used to reach BattlEye RCon. |
| `rcon_port` | The BattlEye RCon port from your server configuration or hosting panel. |
| `rcon_password` | The BattlEye RCon password. |
| `discord_webhook_url` | An optional Discord webhook. Leave it empty to disable Discord reports for this server. |
| `poll_interval_seconds` | How often connected players are rescanned. The default is 15 seconds. |

### Protection settings

| Setting | Description |
| --- | --- |
| `custom_blocked_ips` | Your own IPv4 addresses and ranges to block. |
| `whitelisted_guids` | BattlEye GUIDs belonging to trusted players who may use a flagged IP. |
| `kick_message` | Message shown for an automatic VPN or datacenter match. |
| `custom_kick_message` | Message shown for a match from your custom blocklist. |
| `debug_mode` | Reports matches without kicking when set to `true`. |
| `mask_ip_in_discord` | Hides part of player IP addresses in Discord. Local logs still contain full IPs. |
| `config_reload_interval_seconds` | How often the configuration is checked for supported live changes. |

The default IP list URLs, update interval, cache directory, and log directory normally do not need to be changed.

## Safe first run

The example configuration starts with `debug_mode` set to `true`. In this mode, the protector connects and reports what it would do, but does not kick anyone.

After starting it:

1. Confirm the output says the IP lists were loaded.
2. Confirm it connected to every configured DayZ server.
3. Join a server and check its log in `data/logs`.
4. Review any detected addresses and Discord reports.
5. Change `debug_mode` to `false` when you are ready to enforce kicks.

The running app picks up the debug mode change within 30 seconds by default. Check `data/logs/app.log` for confirmation that the setting was reloaded.

## Custom blocklist

Add individual IPv4 addresses or CIDR ranges to `custom_blocked_ips`:

```json
"custom_blocked_ips": [
  "203.0.113.5",
  "198.51.100.0/24"
]
```

The first entry blocks one address. The second blocks the specified range. Custom matches use `custom_kick_message`, making them easy to distinguish from automatic list matches.

Changes to the custom blocklist are applied while the protector is running.

## GUID whitelist

Add trusted players to `whitelisted_guids` when they should be allowed even if their IP is flagged:

```json
"whitelisted_guids": [
  "c779d3141c0adcb906e45948212c5b3f"
]
```

GUID matching is not case-sensitive. You can find a player's BattlEye GUID in the server-specific log under `data/logs`.

A whitelisted match is recorded locally, but the player is not kicked and no kick report is sent to Discord. BattlEye must provide the player's GUID before the whitelist can be applied, so test new entries in debug mode before relying on them.

Whitelist changes are applied while the protector is running.

## Multiple DayZ servers

Add another object to the `servers` list for each server you want to protect:

```json
"servers": [
  {
    "name": "Chernarus Main",
    "host": "192.168.1.10",
    "rcon_port": 2302,
    "rcon_password": "first-password",
    "discord_webhook_url": "",
    "poll_interval_seconds": 15
  },
  {
    "name": "Livonia Main",
    "host": "192.168.1.10",
    "rcon_port": 2402,
    "rcon_password": "second-password",
    "discord_webhook_url": "",
    "poll_interval_seconds": 15
  }
]
```

Every server name must be unique. Each server can have its own RCon details, Discord webhook, and scan interval.

## Live configuration changes

The following settings update automatically while the protector is running:

- `kick_message`
- `custom_kick_message`
- `custom_blocked_ips`
- `whitelisted_guids`
- `debug_mode`
- `mask_ip_in_discord`

They are checked every `config_reload_interval_seconds`, which defaults to 30 seconds. Successful changes are written to `app.log`. If the edited JSON is invalid, the current settings remain active and the error is logged.

Restart the protector after changing any of these:

- Server names, addresses, ports, passwords, webhooks, or scan intervals
- IP list settings
- `config_reload_interval_seconds`
- `log_dir`

For Docker, restart with:

```text
docker compose restart
```

## Logs and Discord reports

Logs are stored in `data/logs` by default:

- `app.log` contains startup, RCon connection, list update, and configuration reload information.
- Each configured server has its own log containing player joins, IP addresses, BattlEye GUIDs, matches, and kick results.

Log files rotate automatically to prevent unlimited growth.

Discord kick reports include the server, player name, IP address, BattlEye GUID, matched list, and kick reason. With `mask_ip_in_discord` enabled, part of the IP is hidden in Discord. Local logs always keep the full address.

Treat `data/config.json` and the log files as private. The configuration contains your RCon password and may contain a Discord webhook. Logs contain player IP addresses and GUIDs.

## Troubleshooting

### RCon login refused

Confirm that `rcon_password` exactly matches the BattlEye RCon password, including capitalization.

### The protector cannot connect to RCon

Check the host and port, confirm the DayZ server is running, and make sure the firewall permits the connection. Confirm that you entered the RCon port rather than only the game or query port.

If you use Docker, remember that `127.0.0.1` points to the container and normally cannot reach a DayZ server outside it.

### No players are detected

Look for a successful RCon connection in `data/logs/app.log` and the server-specific log. If RCon is connected, confirm `poll_interval_seconds` is set to a reasonable value such as 15.

### IP lists fail to download

Confirm the machine has internet access. After a successful download, each source can fall back to its cached copy during an outage. On a new installation without a cache, a failed source remains empty until a later update succeeds.

### A legitimate player is matched

Keep debug mode enabled while reviewing detections. Add trusted players to `whitelisted_guids`, or disable the supplementary residential VPN list by setting `oooninja_enabled` to `false` and restarting the protector.

### Configuration changes are not applied

Check `app.log` for an invalid JSON error or a warning that the changed setting requires a restart. The live reload interval itself only changes after a restart.

### Another instance is already running

Only one process can use the same configuration file at a time. Stop the existing process or container before starting another one.

## Limitations

- Only IPv4 addresses are checked.
- No list can identify every VPN or proxy.
- IP list matches can produce false positives.
- GUID whitelisting depends on BattlEye providing the GUID before enforcement.

## Support

For help, join the [Italiano DayZ Discord](https://dsc.gg/italianodayz).

## License

Released under the [MIT License](LICENSE).
