# -*- coding: utf-8 -*-
# Copyright (C) 2026 R1BQE
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Shared helper for loading the add-on's pure-Python submodules directly by
file path, bypassing ``globalPlugins.Text_Fixer.__init__`` (which imports
NVDA-only modules and can therefore not be imported outside NVDA)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ADDON_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "addon" / "globalPlugins" / "Text_Fixer"


def loadAddonModule(moduleFileName: str) -> ModuleType:
	"""Load ``moduleFileName`` (e.g. ``"textCleanup.py"``) from the add-on's
	package directory as a standalone module."""
	modulePath = _ADDON_PACKAGE_DIR / moduleFileName
	moduleName = f"text_fixer_under_test_{modulePath.stem}"
	spec = importlib.util.spec_from_file_location(moduleName, modulePath)
	if spec is None or spec.loader is None:
		raise ImportError(f"Could not load module from {modulePath}")
	module = importlib.util.module_from_spec(spec)
	sys.modules[moduleName] = module
	spec.loader.exec_module(module)
	return module
