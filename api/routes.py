from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, Response

from core.steel.beam import calculate_steel_beam
from core.steel.column import calculate_steel_column
from core.timber.beam import calculate_timber_beam
from models.steel import (
    MemberScheduleRequest,
    SteelBeamApiResponse,
    SteelBeamRequest,
    SteelColumnApiResponse,
    SteelColumnRequest,
)
from models.timber import TimberBeamApiResponse, TimberBeamRequest
from reports.generators.member_schedule_excel import generate_member_schedule_excel
from reports.generators.member_schedule_report import generate_member_schedule_pdf_report
from reports.generators.steel_beam_report import generate_steel_beam_pdf_report
from reports.generators.timber_beam_report import generate_timber_beam_pdf_report
from reports.generators.steel_column_report import generate_steel_column_pdf_report
from utils.api_errors import api_response, friendly_engineering_error


router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return api_response(success=True, results={"status": "ok"})


@router.post("/calculate/steel-beam", response_model=SteelBeamApiResponse)
async def steel_beam(payload: SteelBeamRequest) -> dict | JSONResponse:
    try:
        return calculate_steel_beam(payload)
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[steel-beam] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[steel-beam] exception:",
            {
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
        raise


@router.post("/reports/steel-beam", response_model=None)
async def steel_beam_report(payload: SteelBeamRequest):
    print("[steel-beam-report] report payload:", payload.model_dump(mode="json"))
    try:
        calculation_response = calculate_steel_beam(payload)
        print(
            "[steel-beam-report] generated result structure:",
            {
                "success": calculation_response.get("success"),
                "result_keys": sorted((calculation_response.get("results") or {}).keys()),
                "warning_count": len(calculation_response.get("warnings") or []),
            },
        )
        report = generate_steel_beam_pdf_report(
            request_data=payload.model_dump(mode="json"),
            calculation_response=calculation_response,
        )
        print("[steel-beam-report] export success:", {"filename": report.filename, "bytes": len(report.content)})
        return Response(
            content=report.content,
            media_type=report.media_type,
            headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
        )
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[steel-beam-report] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[steel-beam-report] export failure:",
            {
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=api_response(success=False, errors=["Steel beam PDF report could not be generated."]),
        )


@router.post("/calculate/steel-column", response_model=SteelColumnApiResponse)
async def steel_column(payload: SteelColumnRequest) -> dict | JSONResponse:
    try:
        return calculate_steel_column(payload)
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[steel-column] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[steel-column] exception:",
            {
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
        raise


@router.post("/reports/steel-column", response_model=None)
async def steel_column_report(payload: SteelColumnRequest):
    print("[steel-column-report] report payload:", payload.model_dump(mode="json"))
    try:
        calculation_response = calculate_steel_column(payload)
        print(
            "[steel-column-report] generated result structure:",
            {
                "success": calculation_response.get("success"),
                "result_keys": sorted((calculation_response.get("results") or {}).keys()),
                "warning_count": len(calculation_response.get("warnings") or []),
            },
        )
        report = generate_steel_column_pdf_report(
            request_data=payload.model_dump(mode="json"),
            calculation_response=calculation_response,
        )
        print("[steel-column-report] export success:", {"filename": report.filename, "bytes": len(report.content)})
        return Response(
            content=report.content,
            media_type=report.media_type,
            headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
        )
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[steel-column-report] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[steel-column-report] export failure:",
            {
                "exception_type": type(exc).__name__,
                "exception": str(exc),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=api_response(success=False, errors=["Steel column PDF report could not be generated."]),
        )


@router.post("/reports/member-schedule", response_model=None)
async def member_schedule_report(payload: MemberScheduleRequest):
    print(
        "[member-schedule-report] report request:",
        {
            "project_name": payload.project_name,
            "orientation": payload.orientation,
            "member_count": len(payload.members),
        },
    )
    try:
        # Renders the project schedule from saved member data only; no recalculation.
        report = generate_member_schedule_pdf_report(request_data=payload.model_dump(mode="json"))
        print("[member-schedule-report] export success:", {"filename": report.filename, "bytes": len(report.content)})
        return Response(
            content=report.content,
            media_type=report.media_type,
            headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
        )
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[member-schedule-report] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[member-schedule-report] export failure:",
            {"exception_type": type(exc).__name__, "exception": str(exc)},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=api_response(success=False, errors=["Member schedule PDF report could not be generated."]),
        )


@router.post("/reports/member-schedule-excel", response_model=None)
async def member_schedule_excel(payload: MemberScheduleRequest):
    print(
        "[member-schedule-excel] export request:",
        {"project_name": payload.project_name, "member_count": len(payload.members)},
    )
    try:
        # Renders the project schedule workbook from saved member data only; no recalculation.
        workbook = generate_member_schedule_excel(request_data=payload.model_dump(mode="json"))
        print("[member-schedule-excel] export success:", {"filename": workbook.filename, "bytes": len(workbook.content)})
        return Response(
            content=workbook.content,
            media_type=workbook.media_type,
            headers={"Content-Disposition": f'attachment; filename="{workbook.filename}"'},
        )
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[member-schedule-excel] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print(
            "[member-schedule-excel] export failure:",
            {"exception_type": type(exc).__name__, "exception": str(exc)},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=api_response(success=False, errors=["Member schedule Excel workbook could not be generated."]),
        )


@router.get("/timber/options")
async def timber_options() -> dict:
    # Drives the Timber Beam dropdowns from the database so new grades/sections appear
    # in the UI without any frontend code change.
    from core.timber.sections import load_materials, load_sections

    return api_response(
        success=True,
        results={
            "grades": [
                {"grade": m["grade"], "type": m["type"]}
                for m in load_materials()
            ],
            "sections": [
                {"name": s["name"], "width_mm": s["width_mm"], "depth_mm": s["depth_mm"]}
                for s in load_sections()
            ],
        },
    )


@router.post("/calculate/timber-beam", response_model=TimberBeamApiResponse)
async def timber_beam(payload: TimberBeamRequest) -> dict | JSONResponse:
    try:
        return calculate_timber_beam(payload)
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[timber-beam] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print("[timber-beam] exception:", {"exception_type": type(exc).__name__, "exception": str(exc)})
        raise


@router.post("/reports/timber-beam", response_model=None)
async def timber_beam_report(payload: TimberBeamRequest):
    print("[timber-beam-report] report payload:", payload.model_dump(mode="json"))
    try:
        calculation_response = calculate_timber_beam(payload)
        report = generate_timber_beam_pdf_report(
            request_data=payload.model_dump(mode="json"),
            calculation_response=calculation_response,
        )
        print("[timber-beam-report] export success:", {"filename": report.filename, "bytes": len(report.content)})
        return Response(
            content=report.content,
            media_type=report.media_type,
            headers={"Content-Disposition": f'attachment; filename="{report.filename}"'},
        )
    except ValueError as exc:
        error = friendly_engineering_error(str(exc))
        print("[timber-beam-report] validation failure:", error)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=api_response(success=False, errors=[error]),
        )
    except Exception as exc:
        print("[timber-beam-report] export failure:", {"exception_type": type(exc).__name__, "exception": str(exc)})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=api_response(success=False, errors=["Timber beam PDF report could not be generated."]),
        )


@router.post("/calculate/load-combinations")
async def load_combinations() -> dict:
    return api_response(
        success=True,
        results={
            "phase": 2,
            "status": "planned",
            "message": "Load-combination API scaffolding is in place for Phase 2.",
        },
    )
