"""Transitional compatibility namespace (C2 structural consolidation).

Re-exports ``raceintel.model_lab`` so frozen pickle class paths
(``v2.model_lab.preprocessing.FittedPreprocessor``) keep loading.
See ``v2/__init__.py``. Do NOT add new code here.
"""

from raceintel.model_lab import *  # noqa: F401,F403
