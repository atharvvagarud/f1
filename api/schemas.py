"""HTTP request schemas (R4 foundation refactor).

Pydantic contracts moved verbatim from ``api/main.py``. Field names, types
and validation behaviour are frozen by the R2 suite (including 422 handling)
— do not tighten or rename without an explicit, approved reason.
"""

from pydantic import BaseModel


class RaceRequest(BaseModel):
    year: int
    event: str


class SingleModelRequest(BaseModel):
    year: int
    event: str
    model: str
