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

from collections.abc import Mapping, Sequence


#: For a given layout, maps a virtual-key code to the (unshifted, shifted)
#: character produced by that key under that layout.
LayoutCharTable = Mapping[int, tuple[str, str]]


def build_directional_mapping(
	tableSource: LayoutCharTable,
	tableTarget: LayoutCharTable,
) -> dict[str, str]:
	"""Build a source->target character mapping between two layouts.

	For every virtual-key code present in both tables, the character produced
	under ``tableSource`` at a given shift state is mapped to the character
	produced under ``tableTarget`` at the same physical key and shift state.

	Unlike a bidirectional mapping, only one direction is produced, so symbols
	that sit on *different* physical keys in the two layouts (e.g. "?" on 7 in
	Russian but on "/" in English) convert deterministically instead of
	colliding and giving a result that depends on layout iteration order. The
	caller decides which layout is the source - see
	:func:`detect_source_layout_index`.
	"""
	mapping: dict[str, str] = {}
	for vk, (unshiftedSource, shiftedSource) in tableSource.items():
		targetChars = tableTarget.get(vk)
		if targetChars is None:
			continue
		unshiftedTarget, shiftedTarget = targetChars
		if unshiftedSource and unshiftedTarget:
			mapping[unshiftedSource] = unshiftedTarget
		if shiftedSource and shiftedTarget:
			mapping[shiftedSource] = shiftedTarget
	return mapping


def detect_source_layout_index(
	text: str,
	layoutCharSets: Sequence[set[str]],
	preferred: int | None = None,
) -> int:
	"""Return the index of the layout the text is most likely typed in.

	Each layout is scored by how many of ``text``'s characters that layout's
	keyboard can produce. Letters discriminate strongly (Cyrillic characters
	only exist in the Russian table, Latin only in the English table), so the
	highest-scoring layout is the source. Returns -1 when no layout produces
	any character of the text. ``preferred`` (the active layout) breaks ties,
	since punctuation-only text is assumed to have been typed in whatever
	layout is currently active.
	"""
	scores = [sum(1 for ch in text if ch in charset) for charset in layoutCharSets]
	if not any(scores):
		return -1
	best = max(range(len(scores)), key=lambda i: scores[i])
	if preferred is not None and 0 <= preferred < len(scores) and scores[preferred] == scores[best]:
		return preferred
	return best


def convert_text(text: str, mapping: Mapping[str, str]) -> str:
	"""Convert ``text`` character by character using ``mapping``.

	Characters that are not present in the mapping (spaces, digits, shared
	punctuation, etc.) are left unchanged.
	"""
	return "".join(mapping.get(ch, ch) for ch in text)
