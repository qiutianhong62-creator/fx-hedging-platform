class ForecastError(Exception):
    code = "forecast_error"
    message = "到期汇率预测失败"
    status_code = 503


class ForecastFetchError(Exception):
    pass


class ForecastAnchorRequiredError(Exception):
    pass


class ForecastMaturityInvalidError(ForecastError):
    code = "forecast_maturity_invalid"
    message = "到期日必须在未来1天至365天之内"
    status_code = 422


class ForecastHorizonInsufficientError(ForecastError):
    code = "forecast_horizon_insufficient"
    message = "ING预测期限不足，无法覆盖该到期日"
    status_code = 503


class ForecastSourceUnavailableError(ForecastError):
    code = "forecast_source_unavailable"
    message = "ING预测数据暂时不可用，请稍后重试"
    status_code = 503


class ForecastSourceInvalidError(ForecastError):
    code = "forecast_source_invalid"
    message = "ING预测页面格式异常，请稍后重试"
    status_code = 502


class ForecastSourceStaleError(ForecastError):
    code = "forecast_source_stale"
    message = "ING预测已超过45天未更新"
    status_code = 503
