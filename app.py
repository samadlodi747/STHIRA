from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routes import router as calculation_router
from utils.api_errors import api_response, friendly_http_error, friendly_validation_errors


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Structural Engineering Calculator",
    version="0.1.0",
    description=(
        "Incremental FastAPI migration of the existing beam, column, "
        "timber and load-combination calculator."
    ),
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(calculation_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = friendly_validation_errors(exc.errors())
    print(
        "[api] validation failure:",
        {
            "path": request.url.path,
            "errors": errors,
            "raw_errors": exc.errors(),
        },
    )
    return JSONResponse(
        status_code=422,
        content=api_response(success=False, errors=errors),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error = friendly_http_error(exc.detail, exc.status_code)
    print(
        "[api] http exception:",
        {
            "path": request.url.path,
            "status_code": exc.status_code,
            "error": error,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=api_response(success=False, errors=[error]),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    print(
        "[api] unhandled exception:",
        {
            "path": request.url.path,
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        },
    )
    return JSONResponse(
        status_code=500,
        content=api_response(
            success=False,
            errors=["The calculation service encountered a backend error."],
        ),
    )


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "index.html", media_type="text/html")
