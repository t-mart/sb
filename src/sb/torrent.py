from pathlib import Path
from dataclasses import dataclass
import hashlib
from typing import Literal

import bencodepy

type HashVersion = Literal["v1", "v2"]


@dataclass
class HashInfo:
    """Stores the info hash value and its version."""

    version: HashVersion
    value: bytes

    @property
    def hex(self) -> str:
        """Returns the hex-encoded string representation of the hash."""
        return self.value.hex()


@dataclass
class TorrentFile:
    length: int
    path: Path

    @classmethod
    def from_files_dict(cls, file_entry: dict[bytes, int | list[bytes]], root: Path):
        length = file_entry.get(b"length")
        path_segments = file_entry.get(b"path")
        path = root / Path(*[segment.decode("utf-8") for segment in path_segments])
        return cls(length=length, path=path)


@dataclass
class Torrent:
    name: Path
    files: list[TorrentFile]
    piece_length: int
    infohash_v1: bytes  # we only support v1 for now
    pieces: list[bytes]

    @classmethod
    def from_file(cls, file_path: Path):
        with open(file_path, "rb") as f:
            torrent_data = bencodepy.decode(f.read())

        info: dict = torrent_data.get(b"info")
        if info is None:
            raise ValueError("Invalid torrent file: missing 'info' dictionary.")

        # The info hash is calculated from the raw bencoded bytes of the 'info' dict
        raw_info_bencoded = bencodepy.encode(info)

        # --- Detect v1/v2 and calculate info hashes ---
        pieces: list[bytes] | None = None

        # Check for v1 (BEP 3)
        if b"pieces" not in info:
            raise ValueError("Unsupported torrent: missing 'pieces' for v1 torrent.")
        infohash_v1 = hashlib.sha1(raw_info_bencoded).digest()

        # Parse the v1 piece hashes
        pieces_value = info.get(b"pieces")
        pieces = [pieces_value[i : i + 20] for i in range(0, len(pieces_value), 20)]

        name = Path(info.get(b"name").decode("utf-8"))
        piece_length = info.get(b"piece length")

        files_value = info.get(b"files")
        if files_value is None:
            # Single-file torrent
            files = [TorrentFile(length=info.get(b"length"), path=name)]
        else:
            # Multi-file torrent
            files = [
                TorrentFile.from_files_dict(file, root=name)
                for file in info.get(b"files", [])
            ]

        return cls(
            name=name,
            piece_length=piece_length,
            pieces=pieces,
            files=files,
            infohash_v1=infohash_v1,
        )

    @property
    def size(self) -> int:
        """Total size of all files in the torrent."""
        return sum(file.length for file in self.files)
