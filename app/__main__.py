from .server import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn

    from .config import settings

    uvicorn.run(
        "app.server:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
