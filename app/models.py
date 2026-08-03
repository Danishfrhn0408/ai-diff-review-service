from pydantic import BaseModel, ConfigDict, Field


class ReviewOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "mock"
    maxFindings: int = Field(default=100, ge=0)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    diff: str
    options: ReviewOptions = Field(
        default_factory=ReviewOptions
    )