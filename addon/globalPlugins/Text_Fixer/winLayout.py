# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Windows-specific helpers: enumerate installed keyboard layouts and build a
virtual-key -> character table for a given layout using the Win32 API.

This module is only ever imported and used while running inside NVDA on
Windows. It intentionally has no unit tests of its own: the pure algorithm
that consumes the tables built here (:mod:`layoutConversion`) is what is
unit-tested, using hand-written tables that stand in for what this module
would build from the real API.
"""

import ctypes
from ctypes import wintypes
from typing import NamedTuple

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

HKL = wintypes.HANDLE

user32.GetKeyboardLayoutList.restype = ctypes.c_int
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(HKL)]

user32.ToUnicodeEx.restype = ctypes.c_int
user32.ToUnicodeEx.argtypes = [
	wintypes.UINT,
	wintypes.UINT,
	ctypes.POINTER(ctypes.c_ubyte),
	ctypes.c_wchar_p,
	ctypes.c_int,
	wintypes.UINT,
	HKL,
]

user32.MapVirtualKeyExW.restype = wintypes.UINT
user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, HKL]

kernel32.LCIDToLocaleName.restype = ctypes.c_int
kernel32.LCIDToLocaleName.argtypes = [wintypes.LCID, ctypes.c_wchar_p, ctypes.c_int, wintypes.DWORD]

kernel32.GetLocaleInfoEx.restype = ctypes.c_int
kernel32.GetLocaleInfoEx.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_int]

_MAPVK_VK_TO_VSC = 0
_VK_SHIFT = 0x10
_LOCALE_SLOCALIZEDDISPLAYNAME = 0x00000002


class LayoutInfo(NamedTuple):
	#: The raw HKL (keyboard layout handle) value, used to build the char table.
	hkl: int
	#: A localized, human-readable name of the layout's language, e.g. "Русский".
	displayName: str


def _get_layout_display_name(hkl: int) -> str:
	"""Best-effort localized language name for a layout, derived from its LANGID."""
	langid = hkl & 0xFFFF
	localeNameBuf = ctypes.create_unicode_buffer(85)
	if kernel32.LCIDToLocaleName(langid, localeNameBuf, len(localeNameBuf), 0) == 0:
		return f"HKL 0x{hkl:08X}"
	displayNameBuf = ctypes.create_unicode_buffer(128)
	written = kernel32.GetLocaleInfoEx(
		localeNameBuf.value,
		_LOCALE_SLOCALIZEDDISPLAYNAME,
		displayNameBuf,
		len(displayNameBuf),
	)
	if written == 0:
		return localeNameBuf.value or f"HKL 0x{hkl:08X}"
	return displayNameBuf.value


def get_installed_layouts() -> list[LayoutInfo]:
	"""Return every keyboard layout currently installed for the logged-on user.

	Uses ``GetKeyboardLayoutList``, so it reflects the layouts actually
	installed in Windows, not a hardcoded list.
	"""
	count = user32.GetKeyboardLayoutList(0, None)
	if count <= 0:
		return []
	bufferType = HKL * count
	buffer = bufferType()
	written = user32.GetKeyboardLayoutList(count, buffer)
	layouts: list[LayoutInfo] = []
	nameCounts: dict[str, int] = {}
	for i in range(written):
		hklValue = buffer[i]
		hkl = int(hklValue) if hklValue else 0
		name = _get_layout_display_name(hkl)
		# Disambiguate two installed layouts that share the same language name
		# (e.g. two English variants) by appending a counter.
		nameCounts[name] = nameCounts.get(name, 0) + 1
		if nameCounts[name] > 1:
			name = f"{name} ({nameCounts[name]})"
		layouts.append(LayoutInfo(hkl=hkl, displayName=name))
	return layouts


def _get_char_for_vk(vk: int, hkl: int, shift: bool) -> str:
	"""Return the single character ``vk`` produces under ``hkl``, or "" if none.

	Uses ``ToUnicodeEx`` with an explicit HKL so the currently *active*
	Windows layout does not need to change to query a different one.
	Dead keys and multi-character results are treated as "no character" -
	AltGr-only characters (e.g. German "@") are a known limitation, see the
	README.
	"""
	keyState = (ctypes.c_ubyte * 256)()
	if shift:
		keyState[_VK_SHIFT] = 0x80
	scanCode = user32.MapVirtualKeyExW(vk, _MAPVK_VK_TO_VSC, hkl)
	buffer = ctypes.create_unicode_buffer(8)
	result = user32.ToUnicodeEx(vk, scanCode, keyState, buffer, len(buffer), 0, hkl)
	if result == 1:
		return buffer[0]
	return ""


# Virtual-key codes covering digits, letters and the standard OEM punctuation
# keys - i.e. every physical key that commonly changes character between
# layouts on a standard keyboard.
_CANDIDATE_VK_CODES: tuple[int, ...] = (
	tuple(range(0x30, 0x3A))  # '0'-'9'
	+ tuple(range(0x41, 0x5B))  # 'A'-'Z'
	+ tuple(range(0xBA, 0xC1))  # OEM_1 .. OEM_PLUS/COMMA/MINUS/PERIOD/2
	+ tuple(range(0xDB, 0xE0))  # OEM_4 .. OEM_8
	+ (0xE2,)  # OEM_102 (the extra key next to left shift on ISO keyboards)
)


def build_layout_char_table(hkl: int) -> dict[int, tuple[str, str]]:
	"""Build the (unshifted, shifted) character table for ``hkl``.

	Consumed by :func:`layoutConversion.build_char_mapping`.
	"""
	table: dict[int, tuple[str, str]] = {}
	for vk in _CANDIDATE_VK_CODES:
		unshifted = _get_char_for_vk(vk, hkl, shift=False)
		shifted = _get_char_for_vk(vk, hkl, shift=True)
		if unshifted or shifted:
			table[vk] = (unshifted, shifted)
	return table


user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []

user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

user32.GetKeyboardLayout.restype = HKL
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]


def get_active_layout_hkl() -> int:
	"""Return the HKL of the keyboard layout currently active for the
	foreground window's thread.

	Used when more than two layouts are installed: the text is assumed to
	have been typed under whichever layout is active now, and is converted
	from that layout into the one the user picks in the dialog.
	"""
	hwnd = user32.GetForegroundWindow()
	threadId = user32.GetWindowThreadProcessId(hwnd, None)
	hkl = user32.GetKeyboardLayout(threadId)
	return int(hkl) if hkl else 0
