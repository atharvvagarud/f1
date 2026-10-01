"""Transitional pickle-compatibility shim (C2 structural consolidation).

The frozen serving artifact references
``v2.model_lab.preprocessing.FittedPreprocessor``. The implementation
moved to ``raceintel.model_lab.preprocessing``; this module re-exports
it so ``joblib.load`` keeps working. Do NOT add new code here.
"""

from raceintel.model_lab.preprocessing import FittedPreprocessor  # noqa: F401
