# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Unit tests for the deterministic text-cleanup algorithm (addon spec, section 21)."""

import unittest

from ._loader import loadAddonModule

textCleanup = loadAddonModule("textCleanup.py")


class TestCleanupSpecExamples(unittest.TestCase):
	"""Every worked example from the add-on specification."""

	def test_capitalizes_first_letter(self):
		self.assertEqual(textCleanup.cleanup("привет"), "Привет")

	def test_capitalizes_after_period(self):
		self.assertEqual(textCleanup.cleanup("привет. как дела"), "Привет. Как дела")

	def test_capitalizes_after_exclamation_and_question_marks(self):
		self.assertEqual(
			textCleanup.cleanup("привет! как дела? хорошо"),
			"Привет! Как дела? Хорошо",
		)

	def test_capitalizes_after_ellipsis(self):
		self.assertEqual(textCleanup.cleanup("привет… как дела"), "Привет… Как дела")

	def test_capitalizes_after_semicolon(self):
		self.assertEqual(textCleanup.cleanup("привет; как дела"), "Привет; Как дела")

	def test_collapses_multiple_spaces(self):
		self.assertEqual(textCleanup.cleanup("привет   мир"), "Привет мир")

	def test_removes_space_before_punctuation(self):
		self.assertEqual(
			textCleanup.cleanup("привет , мир ! как дела ?"),
			"Привет, мир! Как дела?",
		)

	def test_quotes_and_parentheses_are_skipped_to_find_a_letter(self):
		self.assertEqual(
			textCleanup.cleanup('"привет. как дела?" потом ушел.'),
			'"Привет. Как дела?" Потом ушел.',
		)
		self.assertEqual(
			textCleanup.cleanup("(привет. как дела)"),
			"(Привет. Как дела)",
		)

	def test_digit_immediately_after_period_is_not_capitalized(self):
		self.assertEqual(
			textCleanup.cleanup("температура 36.6 градусов. сегодня холодно"),
			"Температура 36.6 градусов. Сегодня холодно",
		)

	def test_capitalizes_first_letter_of_each_line(self):
		self.assertEqual(
			textCleanup.cleanup("первая строка\nвторая строка\nтретья строка"),
			"Первая строка\nВторая строка\nТретья строка",
		)

	def test_leading_non_letters_are_skipped_to_find_first_letter(self):
		self.assertEqual(textCleanup.cleanup(' "привет"'), ' "Привет"')

	def test_quoted_speech_after_a_regular_word_is_capitalized(self):
		self.assertEqual(
			textCleanup.cleanup('он сказал "привет. как дела?" потом ушел.'),
			'Он сказал "Привет. Как дела?" Потом ушел.',
		)


class TestCleanupEdgeCases(unittest.TestCase):
	"""Edge cases explicitly called out in the specification: empty text,
	whitespace-only text, punctuation-only text, digits, URLs, e-mails and
	mixed text. These document actual behaviour rather than assert an
	"ideal" result - see the README for known limitations."""

	def test_empty_text(self):
		self.assertEqual(textCleanup.cleanup(""), "")

	def test_whitespace_only_text(self):
		self.assertEqual(textCleanup.cleanup("   "), " ")
		self.assertEqual(textCleanup.cleanup("\n\n"), "\n\n")

	def test_punctuation_only_text(self):
		self.assertEqual(textCleanup.cleanup("!!!"), "!!!")
		self.assertEqual(textCleanup.cleanup("..."), "...")

	def test_digits_only_text(self):
		self.assertEqual(textCleanup.cleanup("12345"), "12345")

	def test_does_not_crash_on_url(self):
		# Known limitation: the mechanical algorithm does not recognize URLs
		# and will capitalize letters after each ".", same as in ordinary text.
		result = textCleanup.cleanup("see https://example.com/page for details")
		self.assertIsInstance(result, str)

	def test_does_not_crash_on_email(self):
		result = textCleanup.cleanup("contact me at ivan@example.com please")
		self.assertIsInstance(result, str)

	def test_mixed_text_no_crash(self):
		result = textCleanup.cleanup("Текст с number 123, an email a@b.com и т.д.")
		self.assertIsInstance(result, str)

	def test_is_idempotent_on_already_clean_text(self):
		clean = "Привет. Как дела? Хорошо."
		self.assertEqual(textCleanup.cleanup(clean), clean)


if __name__ == "__main__":
	unittest.main(verbosity=2)
