# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Clipboard helpers: full best-effort backup/restore plus simple text
get/set, built directly on the Win32 API through ctypes.

pywin32 (``win32clipboard``) is no longer bundled with recent NVDA releases,
so this module talks to user32/kernel32 directly. ctypes is always available
inside NVDA.
"""

import ctypes
from ctypes import wintypes

import time

from logHandler import log

_OPEN_RETRIES = 15
_OPEN_RETRY_DELAY = 0.02
# Some applications take noticeably longer to place their content on the
# clipboard after a Ctrl+C (heavy web pages, delayed rendering). 0.5 s was
# too tight and produced false "no selection" results.
_CHANGE_POLL_TIMEOUT = 2.5
_CHANGE_POLL_INTERVAL = 0.02

#: Delayed rendering: an application may bump the clipboard sequence number
#: before its data is actually readable. Retry reading briefly instead of
#: giving up on the first NULL/absent format.
_READ_RETRIES = 10
_READ_RETRY_DELAY = 0.03

CF_UNICODETEXT = 13
CF_TEXT = 1

_GMEM_MOVEABLE = 0x0002

_ANSI_FALLBACK_CP = 1252

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.OpenClipboard.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [wintypes.HWND]

user32.CloseClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []

user32.EmptyClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []

user32.EnumClipboardFormats.restype = wintypes.UINT
user32.EnumClipboardFormats.argtypes = [wintypes.UINT]

user32.GetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardData.argtypes = [wintypes.UINT]

user32.SetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]

user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardSequenceNumber.argtypes = []

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]

kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]

kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]

kernel32.GetACP.restype = wintypes.UINT
kernel32.GetACP.argtypes = []


def _read_global_memory(hGlobal: int) -> bytes | None:
	"""Copy the bytes behind a global memory handle into a ``bytes`` object."""
	addr = kernel32.GlobalLock(hGlobal)
	if not addr:
		return None
	try:
		size = kernel32.GlobalSize(hGlobal)
		if size == 0:
			return b""
		return ctypes.string_at(addr, size)
	finally:
		kernel32.GlobalUnlock(hGlobal)


def _alloc_global_memory(data: bytes) -> int | None:
	"""Allocate GMEM_MOVEABLE memory filled with ``data``, returning the handle.

	The caller owns the handle and must free it with ``GlobalFree`` unless it
	is handed over to the clipboard via ``SetClipboardData``, which takes
	ownership on success.
	"""
	size = len(data) or 1  # GlobalAlloc of zero bytes fails
	hGlobal = kernel32.GlobalAlloc(_GMEM_MOVEABLE, size)
	if not hGlobal:
		return None
	addr = kernel32.GlobalLock(hGlobal)
	if not addr:
		kernel32.GlobalFree(hGlobal)
		return None
	try:
		ctypes.memmove(addr, data, len(data))
	finally:
		kernel32.GlobalUnlock(hGlobal)
	return hGlobal


def _openClipboard() -> bool:
	"""Try to open the clipboard, retrying briefly since another process may
	be holding it momentarily."""
	for _attempt in range(_OPEN_RETRIES):
		try:
			if user32.OpenClipboard(None):
				return True
		except Exception:
			pass
		time.sleep(_OPEN_RETRY_DELAY)
	return False


def getSequenceNumber() -> int:
	"""Windows increments this on every clipboard change; used to detect that
	a Ctrl+C actually updated the clipboard instead of guessing with a fixed
	delay."""
	try:
		return user32.GetClipboardSequenceNumber()
	except Exception:
		return -1


def backupClipboard() -> dict[int, bytes]:
	"""Best-effort save of every format currently on the clipboard.

	Some formats (e.g. ones backed by GDI handles) may fail to read; those
	are simply skipped rather than aborting the whole backup, so that at
	least the text content is preserved as required.
	"""
	backup: dict[int, bytes] = {}
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to back it up")
		return backup
	try:
		clipFormat = 0
		while True:
			try:
				clipFormat = user32.EnumClipboardFormats(clipFormat)
			except Exception:
				break
			if not clipFormat:
				break
			try:
				data = _read_global_memory(user32.GetClipboardData(clipFormat))
				if data is not None:
					backup[clipFormat] = data
			except Exception as e:
				log.debug(f"Text Fixer: could not back up clipboard format {clipFormat}: {e}")
	finally:
		user32.CloseClipboard()
	return backup


def restoreClipboard(backup: dict[int, bytes]) -> bool:
	"""Restore a backup produced by :func:`backupClipboard`.

	Always attempted from a ``finally`` block by the caller so the user's
	original clipboard content comes back even if something else failed.
	"""
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to restore it")
		return False
	ok = True
	try:
		try:
			user32.EmptyClipboard()
		except Exception as e:
			log.error(f"Text Fixer: could not empty clipboard while restoring: {e}")
			ok = False
		for clipFormat, data in backup.items():
			try:
				hGlobal = _alloc_global_memory(data)
				if not hGlobal:
					ok = False
					continue
				# On success the clipboard takes ownership of the handle.
				if not user32.SetClipboardData(clipFormat, hGlobal):
					kernel32.GlobalFree(hGlobal)
					ok = False
			except Exception as e:
				log.debug(f"Text Fixer: could not restore clipboard format {clipFormat}: {e}")
				ok = False
	finally:
		user32.CloseClipboard()
	return ok


def _decode_text(data: bytes, encoding: str = "utf-16-le", errors: str = "surrogatepass") -> str:
	"""Decode clipboard bytes into ``str``, dropping the terminator."""
	return data.decode(encoding, errors=errors).rstrip("\x00")


def _get_ansi_codepage() -> int:
	"""Return the system ANSI code page (e.g. 1251 for Russian Windows),
	used to decode CF_TEXT content. Falls back to a sane default."""
	try:
		acp = kernel32.GetACP()
		return acp if acp else _ANSI_FALLBACK_CP
	except Exception:
		return _ANSI_FALLBACK_CP


def _read_clipboard_text() -> str | None:
	"""Read the clipboard's text, preferring CF_UNICODETEXT and falling back
	to CF_TEXT (ANSI) for applications that only provide the legacy format.

	Retries briefly to ride out delayed rendering, where an application
	updates the clipboard sequence number but only serves the actual data a
	moment later."""
	for _attempt in range(_READ_RETRIES):
		if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
			hGlobal = user32.GetClipboardData(CF_UNICODETEXT)
			data = _read_global_memory(hGlobal) if hGlobal else None
			if data is not None:
				return _decode_text(data)
		elif user32.IsClipboardFormatAvailable(CF_TEXT):
			hGlobal = user32.GetClipboardData(CF_TEXT)
			data = _read_global_memory(hGlobal) if hGlobal else None
			if data is not None:
				return _decode_text(data, f"cp{_get_ansi_codepage()}", "replace")
		time.sleep(_READ_RETRY_DELAY)
	return None


def getText() -> str | None:
	"""Return the current text on the clipboard, or ``None`` if there is
	none / it could not be read."""
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to read text")
		return None
	try:
		text = _read_clipboard_text()
		if text is None:
			hasUnicode = bool(user32.IsClipboardFormatAvailable(CF_UNICODETEXT))
			hasAnsi = bool(user32.IsClipboardFormatAvailable(CF_TEXT))
			log.debug(f"Text Fixer: no readable text on clipboard (unicode={hasUnicode}, ansi={hasAnsi})")
		return text
	finally:
		user32.CloseClipboard()


def setText(text: str) -> bool:
	"""Replace the clipboard contents with plain Unicode ``text``."""
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to write text")
		return False
	try:
		try:
			user32.EmptyClipboard()
		except Exception as e:
			log.error(f"Text Fixer: could not empty clipboard while writing text: {e}")
			return False
		data = text.encode("utf-16-le", errors="surrogatepass") + b"\x00\x00"
		hGlobal = _alloc_global_memory(data)
		if not hGlobal:
			return False
		# On success the clipboard takes ownership of the handle.
		if not user32.SetClipboardData(CF_UNICODETEXT, hGlobal):
			kernel32.GlobalFree(hGlobal)
			return False
		return True
	finally:
		user32.CloseClipboard()


def waitForClipboardChange(previousSequence: int, timeout: float = _CHANGE_POLL_TIMEOUT) -> bool:
	"""Poll the clipboard sequence number until it changes from
	``previousSequence`` or ``timeout`` seconds elapse.

	Returns ``True`` if a change was observed. Polling the sequence number is
	more reliable than a fixed sleep, since Ctrl+C completion time varies
	between applications.
	"""
	deadline = time.time() + timeout
	while time.time() < deadline:
		if getSequenceNumber() != previousSequence:
			return True
		time.sleep(_CHANGE_POLL_INTERVAL)
	changed = getSequenceNumber() != previousSequence
	if not changed:
		log.debug("Text Fixer: clipboard did not change within the polling window")
	return changed
