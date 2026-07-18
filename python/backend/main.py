from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.errors import (
    probability_calculation_exception_handler,
    validation_exception_handler,
)
from backend.routes.analysis import router as analysis_router
from backend.routes.inputs import router as inputs_router
from backend.services.distributions import ProbabilityCalculationError


SERVICE_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="企业外汇策略分析 API",
        description="USD/CNY 外汇敞口与策略风险分析后端",
        version=SERVICE_VERSION,
    )
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(
        ProbabilityCalculationError,
        probability_calculation_exception_handler,
    )
    app.include_router(analysis_router)
    app.include_router(inputs_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "fx-hedging-backend",
            "version": SERVICE_VERSION,
        }

    return app


app = create_app()
