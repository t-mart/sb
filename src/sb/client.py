from types import TracebackType
from qbittorrentapi import Client
from qbittorrentapi.torrents import TorrentStatusesT, TorrentFilesT
from pathlib import Path
from typing import Literal, cast

type AddResponse = Literal["Ok.", "Fails."]


class FailedAddException(Exception):
    pass


class QBittorrentClient:
    def __init__(self, host: str, username: str, password: str, category: str | None):
        self.client = Client(host=host, username=username, password=password)
        self.category = category

    def login(self):
        self.client.auth_log_in()

    def logout(self):
        self.client.auth_log_out()

    def __enter__(self):
        self.login()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        self.logout()

    def _add_paused_torrent(self, path_or_data: TorrentFilesT):
        response = cast(
            AddResponse,
            self.client.torrents_add(
                torrent_files=path_or_data,
                category=self.category,
                is_paused=True,
            ),
        )
        if response == "Fails.":
            raise FailedAddException("Failed to add torrent.")

    def add_paused_torrent_by_path(self, path: Path):
        """Add a torrent to the client by file path."""
        return self._add_paused_torrent(str(path))

    def add_paused_torrent_by_data(self, data: bytes):
        """Add a torrent to the client by raw data."""
        return self._add_paused_torrent(data)

    def has_category(self) -> bool:
        """Check if the specified category exists on the client or if no category is specified."""
        return (
            self.category is None or self.category in self.client.torrents_categories()
        )

    def list_torrents(self, status: TorrentStatusesT | None = None):
        return self.client.torrents_info(category=self.category, status_filter=status)

    def start_recheck(self, hash_hex: str):
        """
        Start a recheck for the torrent with the given hash.

        Note that this does not wait for the recheck to complete.
        """
        self.client.torrents_recheck(hashes=hash_hex)

    def export(self, hash_hex: str) -> bytes:
        """Export the raw torrent data for the torrent with the given hash."""
        return self.client.torrents_export(torrent_hash=hash_hex)
    

    def start(self, hash_hex: str):
        """Start the torrent with the given hash."""
        self.client.torrents_start(hashes=hash_hex)
