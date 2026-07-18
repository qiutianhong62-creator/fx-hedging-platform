class MarketDataError(Exception):
    code = "market_data_error"
    message = "市场数据处理失败"
    status_code = 503


class MarketDataFetchError(Exception):
    pass


class MarketDataUnavailableError(MarketDataError):
    code = "market_data_unavailable"
    message = "历史市场数据暂时不可用，请稍后重试"
    status_code = 503


class MarketDataInvalidError(MarketDataError):
    code = "market_data_invalid"
    message = "市场数据格式异常，请稍后重试"
    status_code = 502


class MarketDataInsufficientError(MarketDataError):
    code = "market_data_insufficient"
    message = "历史有效数据不足，暂时无法计算波动率"
    status_code = 503


class MarketDataStaleError(MarketDataError):
    code = "market_data_stale"
    message = "最新市场数据已经过期，暂时无法计算"
    status_code = 503
