# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Unit tests for the pure layout-mapping algorithm (addon spec, section 21).

``winLayout.py`` (which calls the real Win32 ``ToUnicodeEx`` API) is not
imported here, since it only works on Windows inside NVDA. Instead, these
tests use hand-written virtual-key tables that stand in for what
``winLayout.build_layout_char_table`` would return for the standard
ЙЦУКЕН (Russian) and QWERTY (US English) layouts, to verify the
character-mapping algorithm itself.

The tables include the digit and OEM punctuation keys, because the whole point
of the directional mapping is that symbols which live on *different* physical
keys in the two layouts ("?" on 7 in Russian but on "/" in English) convert
deterministically once the source layout is known.
"""

import unittest

from ._loader import loadAddonModule

layoutConversion = loadAddonModule("layoutConversion.py")

# Physical-key correspondence between US QWERTY and standard Russian ЙЦУКЕН,
# for the keys exercised by the specification's test strings.
_EN_TABLE = {
	0x51: ("q", "Q"), 0x57: ("w", "W"), 0x45: ("e", "E"), 0x52: ("r", "R"),
	0x54: ("t", "T"), 0x59: ("y", "Y"), 0x55: ("u", "U"), 0x49: ("i", "I"),
	0x4F: ("o", "O"), 0x50: ("p", "P"),
	0x41: ("a", "A"), 0x53: ("s", "S"), 0x44: ("d", "D"), 0x46: ("f", "F"),
	0x47: ("g", "G"), 0x48: ("h", "H"), 0x4A: ("j", "J"), 0x4B: ("k", "K"),
	0x4C: ("l", "L"),
	0x5A: ("z", "Z"), 0x58: ("x", "X"), 0x43: ("c", "C"), 0x56: ("v", "V"),
	0x42: ("b", "B"), 0x4E: ("n", "N"), 0x4D: ("m", "M"),
	0x30: ("0", ")"), 0x31: ("1", "!"), 0x32: ("2", "@"), 0x33: ("3", "#"),
	0x34: ("4", "$"), 0x35: ("5", "%"), 0x36: ("6", "^"), 0x37: ("7", "&"),
	0x38: ("8", "*"), 0x39: ("9", "("),
	0xBA: (";", ":"), 0xBE: (".", ">"), 0xBF: ("/", "?"),
}

_RU_TABLE = {
	0x51: ("й", "Й"), 0x57: ("ц", "Ц"), 0x45: ("у", "У"), 0x52: ("к", "К"),
	0x54: ("е", "Е"), 0x59: ("н", "Н"), 0x55: ("г", "Г"), 0x49: ("ш", "Ш"),
	0x4F: ("щ", "Щ"), 0x50: ("з", "З"),
	0x41: ("ф", "Ф"), 0x53: ("ы", "Ы"), 0x44: ("в", "В"), 0x46: ("а", "А"),
	0x47: ("п", "П"), 0x48: ("р", "Р"), 0x4A: ("о", "О"), 0x4B: ("л", "Л"),
	0x4C: ("д", "Д"),
	0x5A: ("я", "Я"), 0x58: ("ч", "Ч"), 0x43: ("с", "С"), 0x56: ("м", "М"),
	0x42: ("и", "И"), 0x4E: ("т", "Т"), 0x4D: ("ь", "Ь"),
	0x30: ("0", ")"), 0x31: ("1", "!"), 0x32: ("2", '"'), 0x33: ("3", "№"),
	0x34: ("4", ";"), 0x35: ("5", "%"), 0x36: ("6", ":"), 0x37: ("7", "?"),
	0x38: ("8", "*"), 0x39: ("9", "("),
	0xBA: ("ж", "Ж"), 0xBE: ("ю", "Ю"), 0xBF: (".", ","),
}

_EN_CHARSET = {ch for pair in _EN_TABLE.values() for ch in pair if ch}
_RU_CHARSET = {ch for pair in _RU_TABLE.values() for ch in pair if ch}


class TestDirectionalMapping(unittest.TestCase):
	def test_en_typed_text_converts_to_ru(self):
		mapping = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		self.assertEqual(layoutConversion.convert_text("ghbdtn", mapping), "привет")
		self.assertEqual(layoutConversion.convert_text("rfr ltkf", mapping), "как дела")

	def test_ru_typed_text_converts_to_en(self):
		mapping = layoutConversion.build_directional_mapping(_RU_TABLE, _EN_TABLE)
		self.assertEqual(layoutConversion.convert_text("привет", mapping), "ghbdtn")
		self.assertEqual(layoutConversion.convert_text("как дела", mapping), "rfr ltkf")

	def test_punctuation_converts_by_physical_key(self):
		enToRu = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		ruToEn = layoutConversion.build_directional_mapping(_RU_TABLE, _EN_TABLE)
		# English shifted digits become the standard Russian ones.
		self.assertEqual(
			layoutConversion.convert_text("@#$%^&", enToRu),
			'"№;%:?',
		)
		self.assertEqual(
			layoutConversion.convert_text('"№;%:?', ruToEn),
			"@#$%^&",
		)
		# "/" (EN) and "." (RU) share a physical key.
		self.assertEqual(layoutConversion.convert_text("/", enToRu), ".")
		self.assertEqual(layoutConversion.convert_text(".", ruToEn), "/")

	def test_question_mark_is_deterministic(self):
		# "?" sits on the 7 key in Russian but on the "/" key in English. The
		# directional mapping gives each direction its own answer instead of
		# colliding: the result must not depend on layout iteration order.
		enToRu = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		ruToEn = layoutConversion.build_directional_mapping(_RU_TABLE, _EN_TABLE)
		self.assertEqual(enToRu.get("?"), ",")
		self.assertEqual(ruToEn.get("?"), "&")

	def test_comma_case_round_trips(self):
		# English-typed "dfcz? gtnz? vfif" must become "вася, петя, маша".
		enToRu = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		self.assertEqual(
			layoutConversion.convert_text("dfcz? gtnz? vfif", enToRu),
			"вася, петя, маша",
		)

	def test_directional_mapping_is_not_bidirectional(self):
		enToRu = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		ruToEn = layoutConversion.build_directional_mapping(_RU_TABLE, _EN_TABLE)
		# "в" only maps EN->RU direction-wise from the Russian source.
		self.assertEqual(enToRu.get("в"), None)
		self.assertEqual(ruToEn.get("в"), "d")

	def test_characters_absent_from_both_layouts_are_unchanged(self):
		mapping = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		self.assertEqual(
			layoutConversion.convert_text("privet 123!", mapping),
			"зкшмуе 123!",
		)

	def test_empty_text(self):
		mapping = layoutConversion.build_directional_mapping(_EN_TABLE, _RU_TABLE)
		self.assertEqual(layoutConversion.convert_text("", mapping), "")

	def test_no_shared_virtual_keys_yields_empty_mapping(self):
		self.assertEqual(layoutConversion.build_directional_mapping({}, _RU_TABLE), {})
		self.assertEqual(layoutConversion.build_directional_mapping(_EN_TABLE, {}), {})


class TestSourceDetection(unittest.TestCase):
	def test_latin_text_detects_english(self):
		self.assertEqual(
			layoutConversion.detect_source_layout_index("ghbdtn rfr ltkf", [_EN_CHARSET, _RU_CHARSET]),
			0,
		)

	def test_cyrillic_text_detects_russian(self):
		self.assertEqual(
			layoutConversion.detect_source_layout_index("привет как дела", [_EN_CHARSET, _RU_CHARSET]),
			1,
		)

	def test_punctuation_tie_uses_preferred_layout(self):
		# "?!" exists in both layouts, so the active (preferred) layout wins.
		self.assertEqual(
			layoutConversion.detect_source_layout_index("?!", [_EN_CHARSET, _RU_CHARSET], preferred=1),
			1,
		)
		self.assertEqual(
			layoutConversion.detect_source_layout_index("?!", [_EN_CHARSET, _RU_CHARSET], preferred=0),
			0,
		)

	def test_digits_alone_tie_uses_preferred_layout(self):
		self.assertEqual(
			layoutConversion.detect_source_layout_index("12345", [_EN_CHARSET, _RU_CHARSET], preferred=1),
			1,
		)

	def test_no_matching_characters_returns_minus_one(self):
		self.assertEqual(
			layoutConversion.detect_source_layout_index("§", [_EN_CHARSET, _RU_CHARSET]),
			-1,
		)


if __name__ == "__main__":
	unittest.main(verbosity=2)
