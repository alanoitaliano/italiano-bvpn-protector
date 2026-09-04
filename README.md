# italiano-bvpn-protector

For support, join https://dsc.gg/italianodayz

Kicks players connecting to your DayZ server(s) from datacenter/VPN IP ranges,
via BattlEye RCON. Supports multiple servers, a custom IP blacklist, GUID
whitelisting, Discord notifications, and hot-reloading most settings without
a restart.

## Configuration

On first run the app writes an example config to `data/config.json` and
exits. Edit that file with your server(s) RCON details and Discord
webhook(s), then start it again.

## Running with Docker Compose

```bash
docker compose up -d
```

This starts the container, which reads/writes its config, logs, and cached
IP lists under `./data` on the host (mounted into `/app/data`). On first run
it will write the example config and exit - edit `./data/config.json` and
run `docker compose up -d` again.

Follow logs with:

```bash
docker compose logs -f
```

By default `docker compose up` pulls the published image from GitHub
Container Registry (`ghcr.io/<owner>/italiano-bvpn-protector`). To build the
image locally instead, run `docker compose up -d --build`.

## Published images

Images are built and pushed to GHCR automatically by
[.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml)
on every push to `main` and on version tags (`v*`). Set the repository
visibility of the GHCR package to public (or authenticate with `docker
login ghcr.io`) to pull it.
