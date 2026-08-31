# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""NVDA Text Fixer.

Two global commands that work only on selected text, in any application:

- "Причесать выделенный текст": deterministic, mechanical cleanup of
  capitalization, spacing and punctuation spacing.
- "Переключить раскладку выделенного текста": convert the selected text
  between installed Windows keyboard layouts.
"""

import time

import wx

import api
import controlTypes
import globalPluginHandler
import gui
import keyboardHandler
import tones
import ui
from logHandler import log
from scriptHandler import script

from . import clipboardHelper
from . import layoutConversion
from . import textCleanup
from . import winLayout
from .layoutDialog import LayoutChoiceDialog

_SUCCESS_BEEP = (1000, 60)
_ERROR_BEEP = (200, 100)

# A short pause after sending Ctrl+V, giving the target application time to
# read the clipboard before it is restored to the user's original content.
_PASTE_SETTLE_DELAY = 0.1

_STATUS_OK = "ok"
_STATUS_NO_SELECTION = "no_selection"
_STATUS_COPY_FAILED = "copy_failed"


def _beepSuccess() -> None:
	tones.beep(*_SUCCESS_BEEP)


def _beepError() -> None:
	tones.beep(*_ERROR_BEEP)


def _isFocusInPasswordField() -> bool:
	obj = api.getFocusObject()
	if obj is None:
		return False
	try:
		return controlTypes.State.PROTECTED in obj.states
	except Exception:
		return False


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: category shown for this add-on's commands in the NVDA
	# Input Gestures dialog.
	scriptCategory = _("Text Fixer")

	def _copySelectionText(self) -> tuple[str, str | None]:
		"""Copy the current selection to the clipboard, read it back, then
		restore the user's original clipboard content.

		Returns a ``(status, text)`` tuple. ``status`` is one of
		``_STATUS_OK``, ``_STATUS_NO_SELECTION`` (Ctrl+C produced no
		clipboard change - nothing was selected) or ``_STATUS_COPY_FAILED``
		(the clipboard changed but the text could not be read back).
		"""
		backup = clipboardHelper.backupClipboard()
		try:
			previousSequence = clipboardHelper.getSequenceNumber()
			try:
				keyboardHandler.KeyboardInputGesture.fromName("control+c").send()
			except Exception as e:
				log.error(f"Text Fixer: could not send Ctrl+C: {e}")
				return _STATUS_COPY_FAILED, None
			changed = clipboardHelper.waitForClipboardChange(previousSequence)
			if not changed:
				return _STATUS_NO_SELECTION, None
			text = clipboardHelper.getText()
			if text is None:
				return _STATUS_COPY_FAILED, None
			return _STATUS_OK, text
		finally:
			clipboardHelper.restoreClipboard(backup)

	def _pasteText(self, newText: str) -> bool:
		"""Put ``newText`` on the clipboard, paste it over the current
		selection with Ctrl+V, then restore the user's original clipboard
		content. Returns ``True`` on success."""
		backup = clipboardHelper.backupClipboard()
		try:
			if not clipboardHelper.setText(newText):
				return False
			try:
				keyboardHandler.KeyboardInputGesture.fromName("control+v").send()
			except Exception as e:
				log.error(f"Text Fixer: could not send Ctrl+V: {e}")
				return False
			time.sleep(_PASTE_SETTLE_DELAY)
			return True
		finally:
			clipboardHelper.restoreClipboard(backup)

	def _handleCommand(self, transform) -> None:
		if _isFocusInPasswordField():
			# Translators: reported when trying to use a command in a password field.
			ui.message(_("Это поле пароля. Изменять текст нельзя."))
			return
		status, text = self._copySelectionText()
		if status == _STATUS_NO_SELECTION:
			# Translators: reported when there is no text selected.
			ui.message(_("Нет выделенного текста."))
			return
		if status == _STATUS_COPY_FAILED or text is None:
			# Translators: reported when the selected text could not be retrieved.
			ui.message(_("Не удалось получить выделенный текст."))
			return
		transform(text)

	@script(
		# Translators: name of the command shown in the NVDA Input Gestures dialog.
		description=_("Причесать выделенный текст"),
	)
	def script_cleanupText(self, gesture) -> None:
		self._handleCommand(self._cleanupText)

	@script(
		# Translators: name of the command shown in the NVDA Input Gestures dialog.
		description=_("Переключить раскладку выделенного текста"),
	)
	def script_switchLayout(self, gesture) -> None:
		self._handleCommand(self._switchLayout)

	def _cleanupText(self, text: str) -> None:
		cleaned = textCleanup.cleanup(text)
		if cleaned == text:
			# Translators: reported when a command made no changes to the text.
			ui.message(_("Изменений нет."))
			return
		if self._pasteText(cleaned):
			_beepSuccess()
		else:
			# Translators: reported when the corrected text could not be pasted back.
			ui.message(_("Не удалось вставить исправленный текст."))
			_beepError()

	def _switchLayout(self, text: str) -> None:
		layouts = winLayout.get_installed_layouts()
		if len(layouts) < 2:
			# Translators: reported when there are not enough installed
			# keyboard layouts to convert between.
			ui.message(_("Недостаточно установленных раскладок для переключения."))
			return
		if len(layouts) == 2:
			self._convertBetweenLayouts(text, layouts[0].hkl, layouts[1].hkl)
			return
		# More than two layouts: ask which one to convert into. Showing a wx
		# dialog must happen on the GUI thread, so this continues
		# asynchronously in _askLayoutAndConvert.
		wx.CallAfter(self._askLayoutAndConvert, text, layouts)

	def _askLayoutAndConvert(self, text: str, layouts: list) -> None:
		gui.mainFrame.prePopup()
		try:
			dlg = LayoutChoiceDialog(gui.mainFrame, layouts)
			result = dlg.ShowModal()
			selected = dlg.selectedLayout
			dlg.Destroy()
		finally:
			gui.mainFrame.postPopup()
		if result != wx.ID_OK or selected is None:
			# User pressed Escape/Cancel: leave everything untouched.
			return
		activeHkl = winLayout.get_active_layout_hkl()
		self._convertBetweenLayouts(text, activeHkl, selected.hkl)

	def _convertBetweenLayouts(self, text: str, hklA: int, hklB: int) -> None:
		try:
			tableA = winLayout.build_layout_char_table(hklA)
			tableB = winLayout.build_layout_char_table(hklB)
		except Exception as e:
			log.error(f"Text Fixer: could not build keyboard layout tables: {e}")
			# Translators: reported when the layout conversion could not be performed.
			ui.message(_("Не удалось выполнить преобразование раскладки."))
			_beepError()
			return
		mapping = layoutConversion.build_char_mapping(tableA, tableB)
		converted = layoutConversion.convert_text(text, mapping)
		if converted == text:
			# Translators: reported when a command made no changes to the text.
			ui.message(_("Изменений нет."))
			return
		if self._pasteText(converted):
			_beepSuccess()
		else:
			# Translators: reported when the corrected text could not be pasted back.
			ui.message(_("Не удалось вставить исправленный текст."))
			_beepError()
