from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TestCaseCreate(BaseModel):
    name: str
    base_url: str

class TestStepCreate(BaseModel):
    command: str
    target_selector: Optional[str] = None
    input_value: Optional[str] = None

class TestRunResponse(BaseModel):
    id: str
    test_case_id: int
    status: str
    video_url: Optional[str] = None
    error_log: Optional[str] = None
    executed_at: datetime

    class Config:
        from_attributes = True