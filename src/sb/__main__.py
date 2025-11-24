from pathlib import Path
from typing import get_args, Literal
import json

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
    "client",
)
@click.argument(
    "torrent",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=False,
    nargs=-1,
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
def add(client: str, torrent: tuple[Path], delete_after: bool, dry_run: bool):
    """
    Add TORRENT to CLIENT. CLIENT may be a single client or many separated by commas. One or more
    TORRENT files may be provided.
    """
    config = Config.load_from_file()

    deleteable: dict[Path, bool] = {path: True for path in torrent}

    for client_name in client.split(","):
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

            for torrent_path in torrent:
                click.echo(
                    f"\tAdding torrent {torrent_path}",
                    err=True,
                )
                t = Torrent.from_file(torrent_path)
                torrent_hash = t.infohash_v1.hex()
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
            torrent_data = from_qb.export(hashes=missing_hash)
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
            to_qb.start_recheck(hashes=missing_hash)
            click.echo("\t\t🔍 Started recheck", err=True)


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
    "--status",
    "-s",
    type=click.Choice(get_args(TorrentStatusesT)),
    default=None,
    help="Filter torrents by status",
)
def ls(client: str, hashes: tuple[str], status: TorrentStatusesT | None):
    """List all torrents in CLIENT. May provide zero or more HASHES to select specific torrents."""
    config = Config.load_from_file()
    client_config = get_client_config(config, client)

    with QBittorrentClient(
        host=client_config.url,
        username=client_config.username,
        password=client_config.password,
        category=client_config.category,
    ) as qb_client:
        torrents = qb_client.list_torrents(status=status, hashes=hashes)
        json_list = [dict(t) for t in torrents]
        click.echo(json.dumps(json_list, indent=4))


# This is not an actual status in qbittorrentapi, but it's a useful state to know about
# for us: it's when a torrent has completed (either via download or recheck), but is
# stopped and not seeding. None of the qbittorrentapi statuses capture this exactly.
type RecheckTorrentStatusesT = TorrentStatusesT | Literal["downloading_stopped"]

# ugh, get_args does not work nicely on Literal unions
recheck_torrent_statuses = list(get_args(TorrentStatusesT)) + ["downloading_stopped"]


@sb.command()
@click.argument(
    "client",
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(recheck_torrent_statuses),
    default=None,
    help="Filter torrents by status",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def recheck(client: str, status: RecheckTorrentStatusesT | None, dry_run: bool):
    """
    Recheck all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    downloading_stopped = False
    if status == "downloading_stopped":
        downloading_stopped = True
        status = None

    for client_name in client.split(","):
        client_config = get_client_config(config, client_name)

        with QBittorrentClient(
            host=client_config.url,
            username=client_config.username,
            password=client_config.password,
            category=client_config.category,
        ) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(status=status)

            for torrent in torrents:
                if not dry_run:
                    if downloading_stopped and torrent.state != "stoppedDL":
                        continue
                    qb_client.start_recheck(torrent.hash)
                    click.echo(f"\t🔍 Started recheck of {torrent.name}", err=True)
                else:
                    click.echo(
                        f"\tℹ️ Dry run, not starting recheck of {torrent.name}", err=True
                    )


# This is not an actual status in qbittorrentapi, but it's a useful state to know about
# for us: it's when a torrent has completed (either via download or recheck), but is
# stopped and not seeding. None of the qbittorrentapi statuses capture this exactly.
type StartTorrentStatusesT = TorrentStatusesT | Literal["completed_stopped"]

# ugh, get_args does not work nicely on Literal unions
start_torrent_statuses = list(get_args(TorrentStatusesT)) + ["completed_stopped"]


@sb.command()
@click.argument(
    "client",
)
@click.option(
    "--status",
    "-s",
    type=click.Choice(start_torrent_statuses),
    default=None,
    help="Filter torrents by status",
)
@click.option(
    "--dry-run", is_flag=True, help="Show what would be done without making changes"
)
def start(client: str, status: StartTorrentStatusesT | None, dry_run: bool):
    """
    Start all torrents in specified CLIENT. CLIENT may be a single client or many
    separated by commas.
    """
    config = Config.load_from_file()

    completed_stopped = False
    if status == "completed_stopped":
        completed_stopped = True
        status = None

    for client_name in client.split(","):
        client_config = get_client_config(config, client_name)

        with QBittorrentClient(
            host=client_config.url,
            username=client_config.username,
            password=client_config.password,
            category=client_config.category,
        ) as qb_client:
            click.echo(f"Client '{client_name}'", err=True)

            torrents = qb_client.list_torrents(status=status)

            for torrent in torrents:
                if not dry_run:
                    print(torrent.state)
                    if completed_stopped and torrent.state != "stoppedUP":
                        continue
                    click.echo(f"\t🏃‍➡️ Starting torrent {torrent.name}", err=True)
                    qb_client.start(torrent.hash)
                else:
                    click.echo(
                        f"\tℹ️ Dry run, not starting torrent {torrent.name}", err=True
                    )


def get_client_config(config: Config, client_name: str):
    try:
        return config.clients[client_name]
    except KeyError:
        raise click.ClickException(
            f"Client '{client_name}' not found in configuration."
        )
