from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.forecast.errors import ForecastError
from backend.market.errors import MarketDataError
from backend.services.distributions import ProbabilityCalculationError


FIELD_MESSAGES = {
    "currency_pair": "第一版只支持 USD/CNY",
    "exposure_type": "请选择美元应收、美元应付或持有美元",
    "notional_usd": "美元金额必须大于 0",
    "maturity_date": "到期日必须晚于今天",
    "target_cny": "目标人民币金额必须大于 0",
    "assumed_maturity_spot": "假设到期汇率必须大于 0",
    "assumed_expected_maturity_spot": (
        "假设预计到期汇率必须是大于 0 的有效数字"
    ),
    "assumed_annualized_volatility_pct": (
        "假设年化波动率必须是大于 0 的有效数字"
    ),
}


async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()

    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part != "body"]
        field = location[-1] if location else "request"
        if field in seen:
            continue
        seen.add(field)
        fields.append(
            {
                "field": field,
                "message": FIELD_MESSAGES.get(field, "输入格式不正确"),
            }
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "输入内容有误",
                "fields": fields,
            }
        },
    )


async def probability_calculation_exception_handler(
    _: Request,
    __: ProbabilityCalculationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "probability_calculation_error",
                "message": "当前假设参数超出可计算范围，请降低波动率后重试",
            }
        },
    )


async def market_data_exception_handler(
    _: Request,
    exc: MarketDataError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def forecast_exception_handler(
    _: Request,
    exc: ForecastError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
