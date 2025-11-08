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
    infohash_v1: bytes | None  # v1 info hash (20 bytes)
    infohash_v2: bytes | None  # v2 info hash (32 bytes)
    pieces: list[bytes] | None  # v1 piece hashes (20 bytes each)

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
        infohash_v1: bytes | None = None
        infohash_v2: bytes | None = None
        pieces: list[bytes] | None = None

        # Check for v1 (BEP 3)
        if b"pieces" in info:
            infohash_v1 = hashlib.sha1(raw_info_bencoded).digest()

            # Parse the v1 piece hashes
            pieces_value = info.get(b"pieces")
            pieces = [pieces_value[i : i + 20] for i in range(0, len(pieces_value), 20)]

        # Check for v2 (BEP 52)
        if b"file tree" in info:
            infohash_v2 = hashlib.sha256(raw_info_bencoded).digest()

        if not (infohash_v1 or infohash_v2):
            raise ValueError(
                "Invalid torrent: no v1 ('pieces') or v2 ('file tree') metadata found."
            )
        # -----------------------------------------------

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
            infohash_v2=infohash_v2,
        )

    @property
    def size(self) -> int:
        """Total size of all files in the torrent."""
        return sum(file.length for file in self.files)
    
    @property
    def infohash_v1_hex(self) -> str | None:
        """Hex-encoded v1 info hash, if available."""
        return self.infohash_v1.hex() if self.infohash_v1 else None
    
    @property
    def infohash_v2_hex(self) -> str | None:
        """Hex-encoded v2 info hash, if available."""
        return self.infohash_v2.hex() if self.infohash_v2 else None
