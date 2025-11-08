# sb

Stuff to manage the way I use qbittorrent

## Config

Config in toml format is stored in `~/.config/sb/config.toml`.

```toml
[clients.foo]
host = "http://localhost:8080"
username = "admin"
password = "adminadmin"
category = "redacted"

[clients.bar]
host = "http://otherhost:8080"
username = "user"
password = "pass"
```

## Subcommands

### `add`

Given a directory, add all torrent files in it to a qbittorrent instance in a
paused state. After adding, run a recheck on each newly-added torrent.

This is helpful when new torrents are created or downloaded and we want to add
them.

Example:

```sh
sb add ~/torrents --client foo --client bar --client baz
```

### `cp`

Given:

- A source qbittorrent instance
- A target qbittorrent instance

Add all torrents that are in the source client but not in the target client to
the target client. Just like `add`, the torrents are added in a paused state and
a recheck is run after adding.

Example:

```sh
sb cp foo bar
```
