import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from astrbot.api import logger


class MusicCache:
    """管理插件数据目录中的鼠鼠音乐缓存。"""

    _AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}

    def __init__(self, data_dir: str, max_file_bytes: int = 64 * 1024 * 1024):
        self.cache_dir = Path(data_dir).resolve() / "music_cache"
        self.metadata_path = self.cache_dir / "metadata.json"
        self.max_file_bytes = max(1024 * 1024, int(max_file_bytes))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata: Dict[str, Dict[str, Any]] = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        if not self.metadata_path.exists():
            return {}
        try:
            data = json.loads(self.metadata_path.read_text("utf-8"))
            return {
                str(key): value
                for key, value in data.items()
                if isinstance(value, dict)
            } if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            logger.warning(f"[三角洲音乐缓存] 元数据读取失败：{type(exc).__name__}")
            return {}

    def _save_metadata(self) -> None:
        temporary = self.metadata_path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(self.metadata, ensure_ascii=False, indent=2),
                "utf-8",
            )
            os.replace(temporary, self.metadata_path)
        except OSError as exc:
            logger.warning(f"[三角洲音乐缓存] 元数据保存失败：{type(exc).__name__}")
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _key(song: Dict[str, Any]) -> str:
        download = song.get("download") if isinstance(song.get("download"), dict) else {}
        identity = "\n".join(
            str(value or "")
            for value in (
                song.get("songId") or song.get("id"),
                song.get("fileName") or song.get("title"),
                song.get("artist"),
                song.get("url") or download.get("url"),
            )
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @classmethod
    def _extension(cls, url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        return suffix if suffix in cls._AUDIO_EXTENSIONS else ".mp3"

    def _cached_path(self, entry: Dict[str, Any]) -> Optional[Path]:
        filename = str(entry.get("filename") or "")
        if not filename or Path(filename).name != filename:
            return None
        path = (self.cache_dir / filename).resolve()
        if path.parent != self.cache_dir or not path.is_file():
            return None
        return path

    async def get_or_download(self, song: Dict[str, Any], client: Any) -> Optional[str]:
        key = self._key(song)
        entry = self.metadata.get(key) or {}
        cached = self._cached_path(entry)
        if cached:
            entry["last_access"] = int(time.time())
            self.metadata[key] = entry
            self._save_metadata()
            return str(cached)

        download = song.get("download") if isinstance(song.get("download"), dict) else {}
        url = client.resolve_url(
            song.get("url") or download.get("url") or song.get("audioUrl") or song.get("audio_url") or ""
        )
        fetch_binary = getattr(client, "fetch_binary", None)
        if not url or not callable(fetch_binary):
            return None
        content = await fetch_binary(url, max_bytes=self.max_file_bytes)
        if not content:
            return None

        filename = f"{key}{self._extension(url)}"
        path = self.cache_dir / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        except OSError as exc:
            logger.warning(f"[三角洲音乐缓存] 音频保存失败：{type(exc).__name__}")
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        now = int(time.time())
        self.metadata[key] = {
            "filename": filename,
            "title": str(song.get("title") or song.get("fileName") or "未知歌曲"),
            "artist": str(song.get("artist") or "未知艺术家"),
            "size": len(content),
            "downloaded_at": now,
            "last_access": now,
        }
        self._save_metadata()
        return str(path)

    def clean_expired(self, max_age_days: int = 14) -> int:
        cutoff = int(time.time()) - max(1, int(max_age_days)) * 86400
        removed = 0
        for key, entry in list(self.metadata.items()):
            last_access = int(entry.get("last_access") or entry.get("downloaded_at") or 0)
            if last_access >= cutoff:
                continue
            path = self._cached_path(entry)
            if path:
                try:
                    path.unlink()
                except OSError:
                    continue
            self.metadata.pop(key, None)
            removed += 1
        if removed:
            self._save_metadata()
        return removed

    def stats(self) -> Dict[str, Any]:
        total_size = 0
        valid_files = 0
        stale_keys = []
        for key, entry in self.metadata.items():
            path = self._cached_path(entry)
            if not path:
                stale_keys.append(key)
                continue
            valid_files += 1
            try:
                total_size += path.stat().st_size
            except OSError:
                pass
        for key in stale_keys:
            self.metadata.pop(key, None)
        if stale_keys:
            self._save_metadata()
        return {
            "total_files": valid_files,
            "total_size": total_size,
            "total_size_mb": total_size / 1024 / 1024,
            "metadata_count": len(self.metadata),
        }

    def clear(self) -> Dict[str, Any]:
        before = self.stats()
        removed = 0
        for entry in list(self.metadata.values()):
            filename = str(entry.get("filename") or "")
            if not filename or Path(filename).name != filename:
                continue
            path = (self.cache_dir / filename).resolve()
            if path.parent != self.cache_dir or not path.is_file():
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        self.metadata.clear()
        self._save_metadata()
        return {**before, "removed_files": removed}
