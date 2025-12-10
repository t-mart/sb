# sb

`sb` is a CLI that unlocks the expressivity of scripting against qBittorrent.
The web UI is fine, but tedious for performing bulk operations across multiple
instances.

## Installation

```sh
uv tool install git+https://github.com/t-mart/sb.git
```

## Config

Config in toml format is stored in `~/.config/sb/config.toml`.

```toml
[clients.aClient]
host = "http://localhost:8080"
username = "admin"
password = "adminadmin"
category = "redacted"

[clients.bClient]
host = "http://otherhost:8080"
username = "user"
password = "pass"
```

Clients identify instances of qBittorrent running the web UI. Each client has a
name (like `aClient` or `bClient` above) and connection details.

You may also provide a category for a client. Doing so isolates all operations
to that category. (This helps me because I utilize categories in my workflow.)

## Subcommands

Many commands accept a `--dry-run` option to show what would be done without
making any changes.

The best documentation is the help text for each command. Run
`sb COMMAND --help` to see details.

### `add`

Add all torrent files provided to a client in a stopped state and start a
recheck on each newly-added torrent. Client may be a single client or many
separated by commas. One or more torrent files may be provided.

This is helpful when new torrents are created or downloaded and we want to add
them.

Has a `--delete-after` option to delete the torrent file after adding it
successfully to all provided clients.

Examples:

```sh
sb add aClient path/to/a.torrent
```

```sh
sb add aClient,bClient path/to/*.torrent --delete-after
```

### `cp`

Add all torrents from FROM_CLIENT to TO_CLIENT that do not already exist on
TO_CLIENT. Just like `add`, the torrents are added in a paused state and a
recheck is run after adding.

TO_CLIENT may be a single client or many separated by commas.

Examples:

```sh
sb cp aClient bClient
```

### `ls`

List all torrents in a given qbittorrent instance as JSON.

May also provide torrent hashes to select particular torrents. Accepts a
`--status` option to filter which torrents to list.

Example:

```sh
sb ls aClient
```

### `recheck`

Start a recheck on all torrents for client, which can be a single client or many
separated by commas.

Takes a `--status` option to filter which torrents to recheck. Specially for
this command, the status can also be `downloading_stopped`, which matches
torrents that are stopped but have an unknown or unfinished download state. In
other words, `downloading_stopped` matches torrents that are new or did not
succeed in a recheck.

Example:

```sh
sb recheck aClient --status downloading_stopped
```

### `start`

Start all torrents for client, which can be a single client or many separated by
commas.

Takes a `--status` option to filter which torrents to start. Specially for this
command, the status can also be `completed_stopped` which matches torrents that
are stopped but are known to be complete. In other words, `completed_stopped`
matches torrents that were previously `sb add`ed or `sb cp`ed.

Example:

```sh
sb start aClient --status completed_stopped
```
