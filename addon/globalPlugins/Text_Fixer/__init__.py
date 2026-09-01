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
import globalCommands
import globalPluginHandler
import gui
import keyboardHandler
import textInfos
import tones
import ui
import winUser
from logHandler import log
from scriptHandler import script

from . import clipboardHelper
from . import layoutConversion
from . import textCleanup
from . import winLayout
from .layoutDialog import LayoutChoiceDialog

_SUCCESS_BEEP = (1000, 60)
_ERROR_BEEP = (200, 100)

# A pause after sending Ctrl+V, giving the target application time to read the
# clipboard before it is restored to the user's original content. Deliberately
# generous: the success beep that follows the paste is the signal that the
# action is complete and the user can do anything next, so the app must have
# actually received the text by then.
_PASTE_SETTLE_DELAY = 0.4

# Virtual-key codes used for the raw key injection (winUser has no letter
# constants). KEYEVENTF_KEYUP moved to winBindings in current NVDA, so the
# literal 0x0002 is used here.
_VK_CONTROL = 0x11
_VK_C = 0x43
_VK_V = 0x56
_KEYUP = 0x0002

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
		"""Get the selected text to process.

		Reads the selection directly through NVDA's object model first (no
		clipboard, no injected keys) because other add-ons and application
		overlays can intercept or break Ctrl+C. Falls back to the clipboard
		for objects that expose no selection through TextInfo.

		Returns a ``(status, text)`` tuple with ``status`` one of
		``_STATUS_OK``, ``_STATUS_NO_SELECTION`` (nothing was selected) or
		``_STATUS_COPY_FAILED`` (the selection could not be read).
		"""
		text = self._readSelectionDirect()
		if text is not None:
			log.debug(f"Text Fixer: read selection directly ({len(text)} chars)")
			return _STATUS_OK, text
		backup = clipboardHelper.backupClipboard()
		try:
			previousSequence = clipboardHelper.getSequenceNumber()
			if not self._sendKeyCombo(_VK_C):
				return _STATUS_COPY_FAILED, None
			changed = clipboardHelper.waitForClipboardChange(previousSequence)
			if not changed:
				log.info("Text Fixer: Ctrl+C produced no clipboard change")
				return _STATUS_NO_SELECTION, None
			text = clipboardHelper.getText()
			if text is None:
				log.info("Text Fixer: clipboard changed but no text could be read back")
				return _STATUS_COPY_FAILED, None
			log.debug(f"Text Fixer: copied selection ({len(text)} chars)")
			return _STATUS_OK, text
		finally:
			clipboardHelper.restoreClipboard(backup)

	def _readSelectionDirect(self) -> str | None:
		"""Read the selected text through NVDA's object model - no clipboard,
		no injected keys, so it also works when other add-ons intercept
		Ctrl+C.

		Tries the focused object's real selection first, then a review-cursor
		selection (text marked with NVDA+F9 / the review cursor). Returns
		``None`` when there is no readable selection.
		"""
		obj = api.getFocusObject()
		if obj is not None:
			try:
				info = obj.makeTextInfo(textInfos.POSITION_SELECTION)
				if info is not None and not info.isCollapsed:
					text = info.text
					if text:
						return text
			except Exception as e:
				log.debug(f"Text Fixer: could not read object selection: {e}")
		try:
			return self._readReviewSelection()
		except Exception as e:
			log.debug(f"Text Fixer: could not read review selection: {e}")
			return None

	def _readReviewSelection(self) -> str | None:
		"""Read a review-cursor selection: text marked with NVDA+F9 (start)
		and the review cursor moved to its end, even when the application
		itself has no real selection.

		Also re-applies the range as the application's real selection so the
		later paste replaces exactly the marked text.
		"""
		pos = api.getReviewPosition().copy()
		gc = globalCommands.commands
		startMarker = gc._getReviewCopyStartMarker(pos)
		if startMarker is None:
			return None
		copyMarker = startMarker.copy()
		if pos.compareEndPoints(startMarker, "endToEnd") > 0:
			# Review cursor moved forward from the start marker.
			copyMarker.setEndPoint(startMarker, "startToStart")
			copyMarker.setEndPoint(pos, "endToEnd")
		else:
			# Review cursor is at or before the start marker.
			copyMarker.setEndPoint(pos, "startToStart")
			copyMarker.setEndPoint(startMarker, "endToEnd")
		copyMarker.move(textInfos.UNIT_CHARACTER, 1, endPoint="end")
		if copyMarker.compareEndPoints(copyMarker, "startToEnd") == 0:
			return None
		text = copyMarker.text
		if not text:
			return None
		try:
			copyMarker.updateSelection()
		except Exception as e:
			log.debug(f"Text Fixer: could not re-apply review selection: {e}")
		return text

	def _sendKeyCombo(self, vk: int) -> bool:
		"""Inject Ctrl+<vk> into the foreground application.

		Sends the keys directly with ``keybd_event`` inside NVDA's
		ignore-injection context rather than through
		``KeyboardInputGesture.send()``. NVDA's gesture machinery resolves the
		keyboard layout through the UIA tree (``getInputHkl`` ->
		``windowThreadID``) before injecting, and that walk raises
		``_ctypes.COMError`` in some applications (UWP, Chrome), aborting the
		whole paste/copy. Injecting the keys directly skips that resolution
		entirely.
		"""
		ctrlDown = bool(winUser.getKeyState(winUser.VK_CONTROL) & 0x8000)
		try:
			with keyboardHandler.ignoreInjection():
				if not ctrlDown:
					winUser.keybd_event(winUser.VK_CONTROL, 0, 0, 0)
				winUser.keybd_event(vk, 0, 0, 0)
				winUser.keybd_event(vk, 0, _KEYUP, 0)
				if not ctrlDown:
					winUser.keybd_event(winUser.VK_CONTROL, 0, _KEYUP, 0)
			return True
		except Exception:
			log.exception("Text Fixer: could not inject Ctrl+%#x", vk)
			return False

	def _pasteText(self, newText: str) -> bool:
		"""Put ``newText`` on the clipboard, paste it over the current
		selection with Ctrl+V, then restore the user's original clipboard
		content. Returns ``True`` on success.

		The settle delay is deliberately generous: the target application must
		actually read the clipboard before it is restored, and the success
		beep that follows this call is the signal that the action is complete.
		"""
		backup = clipboardHelper.backupClipboard()
		try:
			if not clipboardHelper.setText(newText):
				return False
			if not self._sendKeyCombo(_VK_V):
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
		# Translators: category shown for this add-on's commands in the NVDA
		# Input Gestures dialog. Kept in sync with `scriptCategory` below.
		category=_("Text Fixer"),
		# Translators: name of the command shown in the NVDA Input Gestures dialog.
		description=_("Причесать выделенный текст"),
	)
	def script_cleanupText(self, gesture) -> None:
		self._handleCommand(self._cleanupText)

	@script(
		# Translators: category shown for this add-on's commands in the NVDA
		# Input Gestures dialog. Kept in sync with `scriptCategory` below.
		category=_("Text Fixer"),
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
		try:
			tables = {layout.hkl: winLayout.build_layout_char_table(layout.hkl) for layout in layouts}
		except Exception as e:
			log.error(f"Text Fixer: could not build keyboard layout tables: {e}")
			# Translators: reported when the layout conversion could not be performed.
			ui.message(_("Не удалось выполнить преобразование раскладки."))
			_beepError()
			return
		sourceHkl = self._detectSourceLayout(text, tables)
		if len(layouts) == 2:
			targetHkl = layouts[1].hkl if layouts[0].hkl == sourceHkl else layouts[0].hkl
			self._convertWithTables(text, tables[sourceHkl], tables[targetHkl])
			return
		# More than two layouts: ask which one to convert into. Showing a wx
		# dialog must happen on the GUI thread, so this continues
		# asynchronously in _askLayoutAndConvert.
		wx.CallAfter(self._askLayoutAndConvert, text, layouts, tables, sourceHkl)

	def _detectSourceLayout(self, text: str, tables: dict) -> int:
		"""Determine which installed layout the text was typed in.

		Scores each layout's character set against the text; letters
		discriminate strongly, so the layout that can produce the most of the
		text is the source. Falls back to the active layout when nothing
		matches (e.g. punctuation-only text).
		"""
		hkls = list(tables)
		charSets = [{ch for pair in table.values() for ch in pair if ch} for table in tables.values()]
		activeHkl = winLayout.get_active_layout_hkl()
		preferred = hkls.index(activeHkl) if activeHkl in hkls else None
		idx = layoutConversion.detect_source_layout_index(text, charSets, preferred)
		if idx < 0:
			return hkls[preferred] if preferred is not None else hkls[0]
		return hkls[idx]

	def _askLayoutAndConvert(self, text: str, layouts: list, tables: dict, sourceHkl: int) -> None:
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
		self._convertWithTables(text, tables[sourceHkl], tables[selected.hkl])

	def _convertWithTables(self, text: str, tableSource: dict, tableTarget: dict) -> None:
		mapping = layoutConversion.build_directional_mapping(tableSource, tableTarget)
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
