from types import TracebackType
from qbittorrentapi import Client
from qbittorrentapi.torrents import TorrentStatusesT, TorrentFilesT
from pathlib import Path
from typing import Literal, cast, Iterable, get_args

from sb.config import ClientConfig

type AddResponse = Literal["Ok.", "Fails."]
type HashList = str | Iterable[str] | None


type SBTorrentStatus = (
    TorrentStatusesT | Literal["stopped_complete"] | Literal["stopped_downloading"]
)
# ugh, get_args does not work nicely on Literal unions
sb_torrent_statuses = list(get_args(TorrentStatusesT)) + [
    "stopped_complete",
    "stopped_downloading",
]


class FailedAddException(Exception):
    pass


class QBittorrentClient:
    def __init__(self, host: str, username: str, password: str):
        self.client = Client(host=host, username=username, password=password)

    @classmethod
    def from_config(cls, config: ClientConfig) -> QBittorrentClient:
        return cls(
            host=config.url,
            username=config.username,
            password=config.password,
        )

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

    def _add_paused_torrent(self, path_or_data: TorrentFilesT, category: str | None):
        response = cast(
            AddResponse,
            self.client.torrents_add(
                torrent_files=path_or_data,  # type: ignore
                category=category,
                is_paused=True,
            ),
        )
        if response == "Fails.":
            raise FailedAddException("Failed to add torrent.")

    def add_paused_torrent_by_path(self, path: Path, category: str | None):
        """Add a torrent to the client by file path."""
        return self._add_paused_torrent(str(path), category)

    def add_paused_torrent_by_data(self, data: bytes, category: str | None):
        """Add a torrent to the client by raw data."""
        return self._add_paused_torrent(data, category)

    def list_torrents(
        self,
        *,
        status_filter: SBTorrentStatus | None = None,
        category_filter: str | None = None,
        hashes: HashList = None,
    ):
        stopped_complete = False
        stopped_downloading = False
        if status_filter == "stopped_complete":
            stopped_complete = True
            status_filter = None
        elif status_filter == "stopped_downloading":
            stopped_downloading = True
            status_filter = None

        torrents = self.client.torrents_info(
            category=category_filter, status_filter=status_filter, hashes=hashes
        )

        if stopped_complete:
            torrents = [t for t in torrents if t.state == "stoppedUP"]
        elif stopped_downloading:
            torrents = [t for t in torrents if t.state == "stoppedDL"]

        return torrents

    def start_recheck(self, hashes: HashList):
        """
        Start a recheck for the torrent with the given hash.

        Note that this does not wait for the recheck to complete.
        """
        self.client.torrents_recheck(hashes=hashes)

    def export(self, torrent_hash: str) -> bytes:
        """Export the raw torrent data for the torrent with the given hash."""
        return self.client.torrents_export(torrent_hash=torrent_hash)

    def start(self, hashes: HashList):
        """Start the torrent with the given hash."""
        self.client.torrents_start(hashes=hashes)
