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
}


class TestLayoutConversion(unittest.TestCase):
	def setUp(self):
		self.mapping = layoutConversion.build_char_mapping(_EN_TABLE, _RU_TABLE)

	def test_en_typed_text_converts_to_ru(self):
		self.assertEqual(layoutConversion.convert_text("ghbdtn", self.mapping), "привет")
		self.assertEqual(layoutConversion.convert_text("rfr ltkf", self.mapping), "как дела")

	def test_ru_typed_text_converts_to_en(self):
		self.assertEqual(layoutConversion.convert_text("привет", self.mapping), "ghbdtn")
		self.assertEqual(layoutConversion.convert_text("как дела", self.mapping), "rfr ltkf")

	def test_direction_does_not_need_to_be_specified(self):
		# The same combined mapping correctly round-trips text typed under
		# either of the two installed layouts - matching the spec's
		# requirement that the currently active layout does not matter.
		for original in ("ghbdtn", "привет", "rfr ltkf", "как дела"):
			converted = layoutConversion.convert_text(original, self.mapping)
			roundTripped = layoutConversion.convert_text(converted, self.mapping)
			self.assertEqual(roundTripped, original)

	def test_characters_absent_from_both_layouts_are_unchanged(self):
		self.assertEqual(
			layoutConversion.convert_text("privet 123!", self.mapping),
			"зкшмуе 123!",
		)

	def test_empty_text(self):
		self.assertEqual(layoutConversion.convert_text("", self.mapping), "")

	def test_mapping_is_symmetric(self):
		reverseMapping = layoutConversion.build_char_mapping(_RU_TABLE, _EN_TABLE)
		for ch, mapped in self.mapping.items():
			self.assertEqual(reverseMapping.get(mapped), ch)

	def test_no_shared_virtual_keys_yields_empty_mapping(self):
		self.assertEqual(layoutConversion.build_char_mapping({}, _RU_TABLE), {})
		self.assertEqual(layoutConversion.build_char_mapping(_EN_TABLE, {}), {})


if __name__ == "__main__":
	unittest.main(verbosity=2)
