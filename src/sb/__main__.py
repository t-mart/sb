from pathlib import Path
from typing import Literal, cast

import click
from qbittorrentapi import Client

from sb.config import Config
from sb.torrent import Torrent

type AddResponse = Literal["Ok.", "Fails."]


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
def add(torrent_dir: Path, client: tuple[str]):
    """Add all torrents in TORRENT_DIR to specified clients."""
    config = Config.load_from_file()

    torrent_paths = list(torrent_dir.glob("*.torrent"))

    for client_name in client:
        client_config = get_client_config(config, client_name)
        qb_client = Client(
            host=client_config.url,
            username=client_config.username,
            password=client_config.password,
        )
        qb_client.auth_log_in()
        click.echo(f"Client '{client_name}'", err=True)

        category = client_config.category
        if not has_category(qb_client, category):
            raise click.ClickException(
                f"Category '{category}' does not exist on client '{client_name}'."
            )

        existing_torrents = qb_client.torrents_info(category=category)

        existing_v1_infohashes = {t.infohash_v1 for t in existing_torrents}
        existing_v2_infohashes = {t.infohash_v2 for t in existing_torrents}
        for torrent_path in torrent_paths:
            click.echo(
                f"\tAdding torrent {torrent_path}",
                err=True,
            )
            torrent = Torrent.from_file(torrent_path)
            already_exists = (
                torrent.infohash_v1_hex
                and torrent.infohash_v1_hex in existing_v1_infohashes
            ) or (
                torrent.infohash_v2_hex
                and torrent.infohash_v2_hex in existing_v2_infohashes
            )
            if already_exists:
                click.echo(
                    "\t\t⚠️ Already exists, skipping",
                    err=True,
                )
                continue

            add_response = cast(
                AddResponse,
                qb_client.torrents_add(
                    torrent_files=str(torrent_path),
                    is_paused=True,
                    category=category,
                ),
            )
            if add_response == "Fails.":
                click.echo("\t\t❌ Failed to add", err=True)
            else:
                click.echo("\t\t✅ Added successfully", err=True)
                qb_client.torrents_recheck(
                    hashes=[torrent.infohash_v1_hex or torrent.infohash_v2_hex]
                )
                click.echo("\t\t🔍 Started recheck", err=True)

        qb_client.auth_log_out()


@sb.command()
@click.argument(
    "from_client",
    type=str,
)
@click.argument(
    "to_client",
    type=str,
)
def cp(from_client: str, to_client: str):
    """Copy all torrents from FROM_CLIENT to TO_CLIENT."""
    config = Config.load_from_file()
    from_client_config = get_client_config(config, from_client)
    to_client_config = get_client_config(config, to_client)

    from_qb = Client(
        host=from_client_config.url,
        username=from_client_config.username,
        password=from_client_config.password,
    )
    to_qb = Client(
        host=to_client_config.url,
        username=to_client_config.username,
        password=to_client_config.password,
    )

    from_qb.auth_log_in()
    to_qb.auth_log_in()

    click.echo(f"Copying torrents from '{from_client}' to '{to_client}'", err=True)

    if not has_category(from_qb, from_client_config.category):
        raise click.ClickException(
            f"Category '{from_client_config.category}' does not exist on client '{from_client}'."
        )
    if not has_category(to_qb, to_client_config.category):
        raise click.ClickException(
            f"Category '{to_client_config.category}' does not exist on client '{to_client}'."
        )

    from_torrents = from_qb.torrents_info(category=from_client_config.category)
    to_torrents = to_qb.torrents_info(category=to_client_config.category)

    from_hashes = {t.hash for t in from_torrents}
    to_hashes = {t.hash for t in to_torrents}

    missing_hashes = from_hashes - to_hashes

    for missing_hash in missing_hashes:
        torrent = from_qb.torrents_export(torrent_hash=missing_hash)

        click.echo(f"\tAdding torrent {missing_hash}", err=True)

        add_response = cast(
            AddResponse,
            to_qb.torrents_add(
                torrent_files=torrent,
                is_paused=True,
                category=to_client_config.category,
            ),
        )

        if add_response == "Fails.":
            click.echo("\t\t❌ Failed to add", err=True)
        else:
            click.echo("\t\t✅ Added successfully", err=True)
            to_qb.torrents_recheck(hashes=[missing_hash])
            click.echo("\t\t🔍 Started recheck", err=True)


def get_client_config(config: Config, client_name: str):
    try:
        return config.clients[client_name]
    except KeyError:
        raise click.ClickException(
            f"Client '{client_name}' not found in configuration."
        )


def has_category(client: Client, category: str | None) -> bool:
    return category is None or category in client.torrents_categories()
