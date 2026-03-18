from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class OpportunityIn(BaseModel):
    external_id: Optional[str] = None
    title: str
    company: str
    location: Optional[str] = None
    salary: Optional[str] = None
    apply_url: HttpUrl
    metadata: dict[str, Any] = Field(default_factory=dict)
