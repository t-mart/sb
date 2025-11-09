from pathlib import Path
from typing import get_args
from collections import defaultdict

import click
from qbittorrentapi.torrents import TorrentStatusesT

from sb.config import Config
from sb.torrent import Torrent
from sb.client import QBittorrentClient, FailedAddException


@click.group()
def sb():
    pass


@sb.command()
@click.argument(
    "torrent_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "--client",
    "-c",
    multiple=True,
    help="Specify which clients to add to",
    required=True,
)
@click.option(
    '--delete-after',
    is_flag=True,
    help="Delete torrent file after adding",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def add(torrent_dir: Path, client: tuple[str], delete_after: bool, dry_run: bool):
    """Add all torrents in TORRENT_DIR to specified clients."""
    config = Config.load_from_file()

    torrent_paths = list(torrent_dir.glob("*.torrent"))
    deleteable: dict[Path, bool] = defaultdict(lambda: True)

    for client_name in client:
        client_config = get_client_config(config, client_name)
        with QBittorrentClient(
            host=client_config.url,
            username=client_config.username,
            password=client_config.password,
            category=client_config.category,
        ) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            existing_torrents = qb_client.list_torrents()
            existing_hashes = {t.hash for t in existing_torrents}

            for torrent_path in torrent_paths:
                click.echo(
                    f"\tAdding torrent {torrent_path}",
                    err=True,
                )
                torrent = Torrent.from_file(torrent_path)
                torrent_hash = torrent.infohash_v1.hex()
                print(torrent_hash)
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
                    qb_client.add_paused_torrent_by_path(torrent_path)
                except FailedAddException:
                    click.echo("\t\t❌ Failed to add", err=True)
                    deleteable[torrent_path] = False
                    continue

                click.echo("\t\t✅ Added successfully", err=True)
                qb_client.start_recheck(torrent_hash)
                click.echo("\t\t🔍 Started recheck", err=True)

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
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def cp(from_client: str, to_client: str, dry_run: bool):
    """Copy all torrents from FROM_CLIENT to TO_CLIENT."""
    config = Config.load_from_file()
    from_client_config = get_client_config(config, from_client)
    to_client_config = get_client_config(config, to_client)

    with (
        QBittorrentClient(
            host=from_client_config.url,
            username=from_client_config.username,
            password=from_client_config.password,
            category=from_client_config.category,
        ) as from_qb,
        QBittorrentClient(
            host=to_client_config.url,
            username=to_client_config.username,
            password=to_client_config.password,
            category=to_client_config.category,
        ) as to_qb,
    ):
        click.echo(f"Copying torrents from '{from_client}' to '{to_client}'", err=True)

        from_torrents = from_qb.list_torrents()
        to_torrents = to_qb.list_torrents()

        from_torrent_map = {t.hash: t for t in from_torrents}

        from_hashes = {t.hash for t in from_torrents}
        to_hashes = {t.hash for t in to_torrents}

        missing_hashes = from_hashes - to_hashes

        for missing_hash in missing_hashes:
            torrent_data = from_qb.export(hash_hex=missing_hash)
            torrent = from_torrent_map[missing_hash]
            click.echo(f"\tAdding torrent: {torrent.name}", err=True)

            if dry_run:
                click.echo("\t\tℹ️ Dry run, not adding", err=True)
                continue

            try:
                to_qb.add_paused_torrent_by_data(
                    torrent_data,
                )
            except FailedAddException:
                click.echo("\t\t❌ Failed to add", err=True)
                continue
            click.echo("\t\t✅ Added successfully", err=True)
            to_qb.start_recheck(hash_hex=missing_hash)
            click.echo("\t\t🔍 Started recheck", err=True)


@sb.command()
@click.argument(
    "client",
    type=str,
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Filter torrents by status",
)
def ls(client: str, status: TorrentStatusesT | None):
    """List all torrents in CLIENT."""
    config = Config.load_from_file()
    client_config = get_client_config(config, client)

    with QBittorrentClient(
        host=client_config.url,
        username=client_config.username,
        password=client_config.password,
        category=client_config.category,
    ) as qb_client:
        existing_torrents = qb_client.list_torrents(status=status)

        for torrent in existing_torrents:
            click.echo(f"{torrent.name} ({torrent.hash})", err=True)


def get_client_config(config: Config, client_name: str):
    try:
        return config.clients[client_name]
    except KeyError:
        raise click.ClickException(
            f"Client '{client_name}' not found in configuration."
        )
