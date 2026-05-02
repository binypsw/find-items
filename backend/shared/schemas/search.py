from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SearchCreate(BaseModel):
    name: str
    raw_query: str
    schedule_cron: Optional[str] = None
    source_filter: Optional[list[str]] = None
    max_price: Optional[int] = None
    min_price: Optional[int] = None


class SearchResponse(BaseModel):
    id: int
    name: str
    raw_query: str
    parsed_query: Optional[dict] = None
    schedule_cron: Optional[str] = None
    is_active: bool
    last_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunResponse(BaseModel):
    run_id: int
    task_id: str
    source_ids: list[str]
