"""Transitional compatibility namespace (C2 structural consolidation).

The implementation package moved ``v2/`` -> ``raceintel/``. This stub
exists for ONE reason: the frozen serving artifact
``results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`` pickles the
class path ``v2.model_lab.preprocessing.FittedPreprocessor``, and
unpickling imports that exact module. The real implementation lives in
``raceintel.model_lab``; this package only re-exports it.

Do NOT add new code here. Remove only when the serving artifact no longer
embeds a ``v2.*`` class path (explicit future migration, never silently).
"""
