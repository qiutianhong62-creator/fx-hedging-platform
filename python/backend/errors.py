from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


FIELD_MESSAGES = {
    "currency_pair": "第一版只支持 USD/CNY",
    "exposure_type": "请选择美元应收、美元应付或持有美元",
    "notional_usd": "美元金额必须大于 0",
    "maturity_date": "到期日必须晚于今天",
    "target_cny": "目标人民币金额必须大于 0",
    "assumed_maturity_spot": "假设到期汇率必须大于 0",
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
