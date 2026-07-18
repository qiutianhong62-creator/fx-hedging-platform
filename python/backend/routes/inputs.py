from fastapi import APIRouter

from backend.models import AnalysisInput, ValidationResponse


router = APIRouter(prefix="/api/v1/inputs", tags=["inputs"])


@router.post("/validate", response_model=ValidationResponse)
def validate_analysis_input(payload: AnalysisInput) -> ValidationResponse:
    return ValidationResponse(normalized_input=payload)
