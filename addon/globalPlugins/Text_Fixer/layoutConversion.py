# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Building and applying a character mapping between two keyboard layouts.

The functions in this module are pure (no Windows/NVDA dependency) and are
unit-tested directly. The Windows-specific code that populates a per-layout
character table using the Win32 API lives in ``winLayout.py`` next to this
module and is only exercised at runtime inside NVDA on Windows.
"""

from collections.abc import Mapping


#: For a given layout, maps a virtual-key code to the (unshifted, shifted)
#: character produced by that key under that layout.
LayoutCharTable = Mapping[int, tuple[str, str]]


def build_char_mapping(tableA: LayoutCharTable, tableB: LayoutCharTable) -> dict[str, str]:
	"""Build a bidirectional character mapping between two layouts.

	For every virtual-key code present in both tables, the character produced
	under ``tableA`` is mapped to the character produced under ``tableB`` at
	the same physical key/shift-state, and vice versa. This lets
	:func:`convert_text` auto-detect the conversion direction character by
	character, since the two layouts' alphabets normally do not overlap.
	"""
	mapping: dict[str, str] = {}
	for vk, (unshiftedA, shiftedA) in tableA.items():
		charsB = tableB.get(vk)
		if charsB is None:
			continue
		unshiftedB, shiftedB = charsB
		if unshiftedA and unshiftedB:
			mapping[unshiftedA] = unshiftedB
			mapping[unshiftedB] = unshiftedA
		if shiftedA and shiftedB:
			mapping[shiftedA] = shiftedB
			mapping[shiftedB] = shiftedA
	return mapping


def convert_text(text: str, mapping: Mapping[str, str]) -> str:
	"""Convert ``text`` character by character using ``mapping``.

	Characters that are not present in the mapping (spaces, digits, shared
	punctuation, etc.) are left unchanged.
	"""
	return "".join(mapping.get(ch, ch) for ch in text)
