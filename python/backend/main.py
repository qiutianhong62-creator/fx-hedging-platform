from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from backend.errors import (
    forecast_exception_handler,
    market_data_exception_handler,
    probability_calculation_exception_handler,
    validation_exception_handler,
)
from backend.forecast.errors import ForecastError
from backend.market.errors import MarketDataError
from backend.routes.analysis import router as analysis_router
from backend.routes.forecast import router as forecast_router
from backend.routes.inputs import router as inputs_router
from backend.routes.market import router as market_router
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
    app.add_exception_handler(ForecastError, forecast_exception_handler)
    app.add_exception_handler(MarketDataError, market_data_exception_handler)
    app.include_router(analysis_router)
    app.include_router(inputs_router)
    app.include_router(market_router)
    app.include_router(forecast_router)

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "fx-hedging-backend",
            "version": SERVICE_VERSION,
        }

    return app


app = create_app()
