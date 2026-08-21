from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ==========================================
# 1. PROJECT SCHEMAS
# ==========================================
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. TEST CASE SCHEMAS
# ==========================================
class TestCaseBase(BaseModel):
    name: str
    base_url: str
    test_type: str = "REGRESSION"
    reference_number: Optional[str] = None
    ut_theme: Optional[str] = None
    ut_function_name: Optional[str] = None
    ut_action: Optional[str] = None
    ut_condition_1: Optional[str] = None
    ut_condition_2: Optional[str] = None
    ut_classification: Optional[str] = None
    ut_how_to_test: Optional[str] = None
    ut_expected_results: Optional[str] = None


class TestCaseCreate(TestCaseBase):
    project_id: int


class TestCaseResponse(TestCaseBase):
    id: int
    project_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. TEST STEP SCHEMAS
# ==========================================
class TestStepBase(BaseModel):
    command: str
    target_selector: Optional[str] = None
    input_value: Optional[str] = None


class TestStepCreate(TestStepBase):
    pass


class TestStepResponse(TestStepBase):
    id: int
    test_case_id: int
    step_order: int

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. TEST RUN SCHEMAS
# ==========================================
class TestRunResponse(BaseModel):
    id: str
    test_case_id: int
    status: str
    video_url: Optional[str] = None
    error_log: Optional[str] = None
    executed_at: datetime

    model_config = ConfigDict(from_attributes=True)