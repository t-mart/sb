from pathlib import Path
from typing import get_args
import json
from functools import cache

import click
from qbittorrentapi.torrents import TorrentStatusesT

from sb.config import Config
from sb.torrent import Torrent
from sb.client import (
    QBittorrentClient,
    FailedAddException,
    SBTorrentStatus,
    sb_torrent_statuses,
)


@click.group()
def sb():
    pass


@sb.command()
@click.argument(
    "client",
)
@click.argument(
    "torrent",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=False,
    nargs=-1,
)
@click.option(
    "-c",
    "--category",
    default=None,
    help="Category to assign to the added torrent(s)",
)
@click.option(
    "--delete-after",
    is_flag=True,
    default=False,
    help="Delete torrent file after successfully adding or being skipped due to already existing by all clients",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def add(
    client: str,
    torrent: tuple[Path],
    category: str | None,
    delete_after: bool,
    dry_run: bool,
):
    """
    Add TORRENT to CLIENT. CLIENT may be a single client or many separated by commas. One or more
    TORRENT files may be provided.
    """
    config = Config.load_from_file()

    deleteable: dict[Path, bool] = {path: True for path in torrent}

    for client_name in client.split(","):
        client_config = get_client_config(config, client_name)
        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            existing_torrents = qb_client.list_torrents()
            existing_hashes = {t.hash for t in existing_torrents}
            recheck_hashes: set[str] = set()

            for torrent_path in torrent:
                click.echo(
                    f"\tAdding torrent {torrent_path}",
                    err=True,
                )
                t = Torrent.from_file(torrent_path)
                torrent_hash = t.infohash_v1.hex()
                if torrent_hash in existing_hashes:
                    click.echo(
                        "\t\t⚠️ Already exists, skipping",
                        err=True,
                    )
                    continue

                if dry_run:
                    click.echo("\t\tℹ️ Dry run, not adding", err=True)
                    continue

                try:
                    qb_client.add_paused_torrent_by_path(
                        torrent_path, category=category
                    )
                except FailedAddException:
                    click.echo("\t\t❌ Failed to add", err=True)
                    deleteable[torrent_path] = False
                    continue

                recheck_hashes.add(torrent_hash)

                click.echo("\t\t✅ Added successfully", err=True)

            if not dry_run:
                qb_client.start_recheck(recheck_hashes)

    if delete_after and not dry_run:
        for torrent_path, can_delete in deleteable.items():
            if can_delete:
                click.echo(f"🗑️ Deleting {torrent_path}", err=True)
                torrent_path.unlink()
            else:
                click.echo(
                    f"Not deleting {torrent_path} due to previous errors",
                    err=True,
                )


@sb.command()
@click.argument(
    "from_client",
    type=str,
)
@click.argument(
    "to_client",
    type=str,
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Only select torrents with this status.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def cp(
    from_client: str,
    to_client: str,
    category_filter: str | None,
    status_filter: SBTorrentStatus | None,
    dry_run: bool,
):
    """
    Copy all torrents from FROM_CLIENT to TO_CLIENT.

    TO_CLIENT may be a single client or many separated by commas.
    """
    config = Config.load_from_file()
    from_client_config = get_client_config(config, from_client)
    to_client_configs = {
        name: get_client_config(config, name) for name in to_client.split(",")
    }

    from_qb = QBittorrentClient.from_config(from_client_config)
    from_qb.login()

    from_torrents = from_qb.list_torrents(
        category_filter=category_filter, status_filter=status_filter
    )
    from_torrent_map = {t.hash: t for t in from_torrents}
    from_hashes = {t.hash for t in from_torrents}

    @cache
    def get_torrent_data(torrent_hash: str) -> bytes:
        return from_qb.export(torrent_hash=torrent_hash)

    for name, config in to_client_configs.items():
        with QBittorrentClient.from_config(config) as to_qb:
            click.echo(f"Copying torrents from '{from_client}' to '{name}'", err=True)

            to_torrents = to_qb.list_torrents()
            to_hashes = {t.hash for t in to_torrents}
            missing_hashes = from_hashes - to_hashes
            recheck_hashes = set(missing_hashes)

            for missing_hash in missing_hashes:
                torrent_data = get_torrent_data(missing_hash)
                torrent = from_torrent_map[missing_hash]
                category = torrent.category
                click.echo(f"\tAdding torrent: {torrent.name}", err=True)

                if dry_run:
                    click.echo("\t\tℹ️ Dry run, not copying", err=True)
                    continue

                try:
                    to_qb.add_paused_torrent_by_data(
                        torrent_data, category=str(category)
                    )
                except FailedAddException:
                    click.echo("\t\t❌ Failed to copy", err=True)
                    recheck_hashes.remove(missing_hash)
                    continue

                click.echo("\t\t✅ Copied successfully", err=True)

            to_qb.start_recheck(hashes=recheck_hashes)

    from_qb.logout()


@sb.command()
@click.argument(
    "client",
    type=str,
)
@click.argument(
    "hashes",
    type=str,
    required=False,
    nargs=-1,
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
def ls(
    client: str,
    hashes: tuple[str],
    status_filter: TorrentStatusesT | None,
    category_filter: str | None,
):
    """List all torrents in CLIENT. May provide zero or more HASHES to select specific torrents."""
    config = Config.load_from_file()
    client_config = get_client_config(config, client)

    with QBittorrentClient.from_config(client_config) as qb_client:
        torrents = qb_client.list_torrents(
            status_filter=status_filter, hashes=hashes, category_filter=category_filter
        )
        json_list = [dict(t) for t in torrents]
        click.echo(json.dumps(json_list, indent=4))


@sb.command()
@click.argument(
    "client",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(sb_torrent_statuses),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def recheck(
    client: str,
    status_filter: SBTorrentStatus | None,
    category_filter: str | None,
    dry_run: bool,
):
    """
    Recheck all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    for client_name in client.split(","):
        client_config = get_client_config(config, client_name)

        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(
                status_filter=status_filter, category_filter=category_filter
            )

            if not dry_run:
                qb_client.start_recheck(torrent.hash for torrent in torrents)

            for torrent in torrents:
                if not dry_run:
                    click.echo(f"\t🔍 Started recheck of {torrent.name}", err=True)
                else:
                    click.echo(f"\tℹ️ Dry run, would recheck {torrent.name}", err=True)


@sb.command()
@click.argument(
    "client",
)
@click.option(
    "-s",
    "--status-filter",
    type=click.Choice(sb_torrent_statuses),
    default=None,
    help="Only select torrents with this status",
)
@click.option(
    "-c",
    "--category-filter",
    default=None,
    help="Only select torrents with this category. Subcategories are included by parent categories.",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def start(
    client: str,
    status_filter: SBTorrentStatus | None,
    category_filter: str | None,
    dry_run: bool,
):
    """
    Start all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    for client_name in client.split(","):
        client_config = get_client_config(config, client_name)

        with QBittorrentClient.from_config(client_config) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(
                status_filter=status_filter, category_filter=category_filter
            )

            if not dry_run:
                qb_client.start(torrent.hash for torrent in torrents)

            for torrent in torrents:
                if not dry_run:
                    click.echo(f"\t🏃‍➡️ Started torrent {torrent.name}", err=True)
                else:
                    click.echo(
                        f"\tℹ️ Dry run, would start torrent {torrent.name}", err=True
                    )


@sb.command()
def lsc():
    """
    List all configured clients as JSON.
    """
    config = Config.load_from_file()

    clients_dict: dict[str, dict[str, str | None]] = {
        name: {
            "url": client.url,
            "username": client.username,
        }
        for name, client in config.clients.items()
    }

    click.echo(json.dumps(clients_dict, indent=2))


def get_client_config(config: Config, client_name: str):
    try:
        return config.clients[client_name]
    except KeyError:
        raise click.ClickException(
            f"Client '{client_name}' not found in configuration."
        )
