from pydantic import BaseModel, Field


class ChecklistStateRequest(BaseModel):
    checks: dict[str, bool] = Field(default_factory=dict)


class ChecklistStateResponse(BaseModel):
    checks: dict[str, bool] = Field(default_factory=dict)
    updatedAt: str = ""
