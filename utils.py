from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, Iterable

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "DNT": "1",  # Do Not Track Request Header
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://kaliscan.io/",  # Important: This might need to be dynamic per manga
}


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:\\"/|?*]', "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.replace("..", ".")
    return cleaned or "untitled"


def ensure_directory(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_chapter_directory(base_dir: Path, manga_title: str, chapter_label: str) -> Path:
    manga_dir = ensure_directory(Path(base_dir) / sanitize_filename(manga_title))
    return ensure_directory(manga_dir / sanitize_filename(chapter_label))


def format_chapter_label(title: str, number: float | None) -> str:
    if number is None:
        return title or "Chapter"
    if float(number).is_integer():
        return f"Chapter {int(number)} - {title}" if title else f"Chapter {int(number)}"
    return f"Chapter {number:g} - {title}" if title else f"Chapter {number:g}"


_logger_configured = False


def get_logger(name: str) -> logging.Logger:
    global _logger_configured
    if not _logger_configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        _logger_configured = True
    return logging.getLogger(name)


class ManifestStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {"chapters": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            data = {"chapters": {}}
        with self._lock:
            self._data = data

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._data, handle, indent=2)
        tmp_path.replace(self.path)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def ensure_chapter(self, chapter_id: str, defaults: Dict[str, Any] | None = None) -> Dict[str, Any]:
        with self._lock:
            chapters = self._data.setdefault("chapters", {})
            entry = chapters.get(chapter_id)
            if entry is None:
                entry = {"status": "pending", "downloaded_pages": []}
                chapters[chapter_id] = entry
            if defaults:
                for key, value in defaults.items():
                    entry.setdefault(key, value)
            self._write()
            return dict(entry)

    def update_chapter(self, chapter_id: str, **fields: Any) -> None:
        with self._lock:
            chapters = self._data.setdefault("chapters", {})
            entry = chapters.get(chapter_id)
            if entry is None:
                entry = {"status": "pending", "downloaded_pages": []}
                chapters[chapter_id] = entry
            entry.update(fields)
            self._write()

    def mark_page_downloaded(self, chapter_id: str, page_index: int) -> None:
        with self._lock:
            chapters = self._data.setdefault("chapters", {})
            entry = chapters.get(chapter_id)
            if entry is None:
                entry = {"status": "pending", "downloaded_pages": []}
                chapters[chapter_id] = entry
            pages: list[int] = entry.setdefault("downloaded_pages", [])
            if page_index not in pages:
                pages.append(page_index)
                pages.sort()
                self._write()

    def chapter_entry(self, chapter_id: str) -> Dict[str, Any]:
        with self._lock:
            chapters = self._data.setdefault("chapters", {})
            entry = chapters.get(chapter_id)
            if entry is None:
                entry = {"status": "pending", "downloaded_pages": []}
                chapters[chapter_id] = entry
                self._write()
            return dict(entry)
