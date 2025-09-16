from langchain_core.pydantic_v1 import BaseModel, Field

class IntentOut(BaseModel):
    motorcycle_loan_intent: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str

class IsMotorcycleOut(BaseModel):
    is_motorcycle: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str

class AppraisalOut(BaseModel):
    appraised_value_thb: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str
