# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Accessible dialog letting the user pick a keyboard layout when more than
two are installed."""

import wx

from .winLayout import LayoutInfo


class LayoutChoiceDialog(wx.Dialog):
	"""A small, fully keyboard-accessible dialog with a single list box of
	installed keyboard layouts."""

	def __init__(self, parent: wx.Window, layouts: list[LayoutInfo]):
		# Translators: title of the dialog used to pick a keyboard layout
		# when more than two are installed.
		super().__init__(parent, title=_("Выбор раскладки"))
		self.layouts = layouts
		self.selectedLayout: LayoutInfo | None = None

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		# Translators: label above the list of installed keyboard layouts.
		labelText = _("Выберите раскладку, в которую нужно преобразовать текст:")
		label = wx.StaticText(self, label=labelText)
		mainSizer.Add(label, flag=wx.ALL, border=10)

		choices = [layout.displayName for layout in layouts]
		self.listBox = wx.ListBox(self, choices=choices, style=wx.LB_SINGLE)
		if choices:
			self.listBox.SetSelection(0)
		mainSizer.Add(self.listBox, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=10)

		buttonSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(buttonSizer, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()

		self.Bind(wx.EVT_BUTTON, self._onOk, id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON, self._onCancel, id=wx.ID_CANCEL)
		self.listBox.Bind(wx.EVT_LISTBOX_DCLICK, self._onOk)
		self.Bind(wx.EVT_CLOSE, self._onCancel)

	def _onOk(self, event: wx.CommandEvent) -> None:
		selection = self.listBox.GetSelection()
		if selection != wx.NOT_FOUND:
			self.selectedLayout = self.layouts[selection]
		self.EndModal(wx.ID_OK)

	def _onCancel(self, event: wx.CommandEvent) -> None:
		self.selectedLayout = None
		self.EndModal(wx.ID_CANCEL)

	def ShowModal(self) -> int:  # noqa: N802 - wx API naming convention
		self.listBox.SetFocus()
		return super().ShowModal()
