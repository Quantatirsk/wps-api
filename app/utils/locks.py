from __future__ import annotations

import asyncio


_writer_lock = asyncio.Lock()
_presentation_lock = asyncio.Lock()
_spreadsheet_lock = asyncio.Lock()


def get_writer_lock() -> asyncio.Lock:
    return _writer_lock


def get_presentation_lock() -> asyncio.Lock:
    return _presentation_lock


def get_spreadsheet_lock() -> asyncio.Lock:
    return _spreadsheet_lock
