from fastapi import FastAPI


SERVICE_VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="企业外汇策略分析 API",
        description="USD/CNY 外汇敞口与策略风险分析后端",
        version=SERVICE_VERSION,
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "fx-hedging-backend",
            "version": SERVICE_VERSION,
        }

    return app


app = create_app()
