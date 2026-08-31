# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Deterministic, mechanical cleanup of selected text.

This module has no dependency on NVDA or any Windows API so it can be
unit tested on any platform.
"""

import re

_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ \t]+([.,!?:;])")
_MULTI_SPACE_RE = re.compile(r" {2,}")

# Characters after which the next letter should be capitalized.
# In addition to the classic sentence-ending punctuation, quotation marks
# are included: NVDA Text Fixer capitalizes the first letter of quoted
# speech (e.g. `он сказал "привет.` -> `Он сказал "Привет.`), matching the
# add-on specification's worked example. This is a deliberate, purely
# mechanical exception - it may occasionally capitalize a word after a
# closing quote that continues the same sentence; see the README for
# known limitations.
_SENTENCE_END_CHARS = frozenset(".!?…;")
_QUOTE_CHARS = frozenset("\"'«»„“”‘’‚‛")
_TRIGGER_CHARS = _SENTENCE_END_CHARS | _QUOTE_CHARS


def cleanup(text: str) -> str:
	"""Mechanically tidy up ``text`` and return the result.

	Rules applied (see the add-on specification for full details):

	1. Remove a space directly before ``. , ! ? : ;``.
	2. Collapse runs of two or more regular spaces into one.
	3. Capitalize the first letter of the text.
	4. Capitalize the first letter after ``. ! ? … ;``/quote characters and
	   after a line break, skipping over spaces/quotes/brackets/other
	   non-letter, non-digit characters, but abandoning the search (without
	   capitalizing anything) if a digit is found before a letter.
	"""
	text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
	text = _MULTI_SPACE_RE.sub(" ", text)

	result: list[str] = []
	capitalizeNext = True
	for ch in text:
		if capitalizeNext:
			if ch.isalpha():
				result.append(ch.upper())
				capitalizeNext = False
				continue
			elif ch.isdigit():
				result.append(ch)
				capitalizeNext = False
				continue
		result.append(ch)
		if ch in _TRIGGER_CHARS or ch == "\n":
			capitalizeNext = True
	return "".join(result)
