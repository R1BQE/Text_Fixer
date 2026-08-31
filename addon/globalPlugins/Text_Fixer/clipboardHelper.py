# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Clipboard helpers: full best-effort backup/restore plus simple text
get/set, built on top of pywin32's ``win32clipboard`` (bundled with NVDA).
"""

import time

import win32clipboard
import win32con
from logHandler import log

_OPEN_RETRIES = 15
_OPEN_RETRY_DELAY = 0.02
_CHANGE_POLL_TIMEOUT = 0.5
_CHANGE_POLL_INTERVAL = 0.02


def _openClipboard() -> bool:
	"""Try to open the clipboard, retrying briefly since another process may
	be holding it momentarily."""
	for _attempt in range(_OPEN_RETRIES):
		try:
			win32clipboard.OpenClipboard()
			return True
		except Exception:
			time.sleep(_OPEN_RETRY_DELAY)
	return False


def getSequenceNumber() -> int:
	"""Windows increments this on every clipboard change; used to detect that
	a Ctrl+C actually updated the clipboard instead of guessing with a fixed
	delay."""
	try:
		return win32clipboard.GetClipboardSequenceNumber()
	except Exception:
		return -1


def backupClipboard() -> dict[int, object]:
	"""Best-effort save of every format currently on the clipboard.

	Some formats (e.g. ones backed by GDI handles) may fail to read; those
	are simply skipped rather than aborting the whole backup, so that at
	least the text content is preserved as required.
	"""
	backup: dict[int, object] = {}
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to back it up")
		return backup
	try:
		clipFormat = 0
		while True:
			try:
				clipFormat = win32clipboard.EnumClipboardFormats(clipFormat)
			except Exception:
				break
			if not clipFormat:
				break
			try:
				backup[clipFormat] = win32clipboard.GetClipboardData(clipFormat)
			except Exception as e:
				log.debug(f"Text Fixer: could not back up clipboard format {clipFormat}: {e}")
	finally:
		win32clipboard.CloseClipboard()
	return backup


def restoreClipboard(backup: dict[int, object]) -> bool:
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
			win32clipboard.EmptyClipboard()
		except Exception as e:
			log.error(f"Text Fixer: could not empty clipboard while restoring: {e}")
			ok = False
		for clipFormat, data in backup.items():
			try:
				win32clipboard.SetClipboardData(clipFormat, data)
			except Exception as e:
				log.debug(f"Text Fixer: could not restore clipboard format {clipFormat}: {e}")
				ok = False
	finally:
		win32clipboard.CloseClipboard()
	return ok


def getText() -> str | None:
	"""Return the current Unicode text on the clipboard, or ``None`` if there
	is none / it could not be read."""
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to read text")
		return None
	try:
		if not win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
			return None
		try:
			return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
		except Exception as e:
			log.error(f"Text Fixer: could not read clipboard text: {e}")
			return None
	finally:
		win32clipboard.CloseClipboard()


def setText(text: str) -> bool:
	"""Replace the clipboard contents with plain Unicode ``text``."""
	if not _openClipboard():
		log.error("Text Fixer: could not open clipboard to write text")
		return False
	try:
		try:
			win32clipboard.EmptyClipboard()
			win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
			return True
		except Exception as e:
			log.error(f"Text Fixer: could not write clipboard text: {e}")
			return False
	finally:
		win32clipboard.CloseClipboard()


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
	return getSequenceNumber() != previousSequence
