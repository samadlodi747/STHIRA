# Structural Calculator Migration Architecture

## Migration Position

This repository is now structured for an incremental migration from the original single-file HTML/CSS/JavaScript calculator into a FastAPI-backed engineering application.

Phase 1 is intentionally narrow:

- Preserve the existing frontend layout, styling, schedule UI and workflows.
- Add a FastAPI backend and route the steel beam calculation through Python.
- Keep the legacy JavaScript calculation available as a fallback while the migration stabilizes.
- Keep column, timber, plotting, reports and AI/PDF processing isolated for later phases.

## Runtime Structure

```text
project/
├── app.py
├── requirements.txt
├── api/
├── core/
│   ├── steel/
│   ├── timber/
│   ├── eurocode/
│   ├── loads/
│   ├── combinations/
│   └── recommendations/
├── models/
├── reports/
├── static/
├── templates/
├── tests/
└── utils/
```

## Layering

`templates/index.html` is the preserved UI from the existing calculator. The new `static/js/api_client.js` adapter collects the steel beam form state and calls `/calculate/steel-beam` with `fetch`.

`api/` owns HTTP concerns only: routing, request validation and phase placeholders.

`models/` owns Pydantic schemas for typed API contracts.

`core/` owns engineering logic. Calculations are kept in explicit SI-compatible units, with section properties converted at the boundary of each formula.

`core/eurocode/` owns EC3/EC5 formula modules. Current Phase 1 implementation includes EC3 section class, axial, shear, bending and simplified LTB helpers.

`core/loads/` owns statics and serviceability solvers.

`core/recommendations/` owns ranking and section-selection policy.

## Migration Roadmap

Phase 1:

- FastAPI app and folder structure.
- Steel beam API endpoint.
- Python EC3 steel beam module.
- Frontend `fetch` integration for steel beam mode.
- Initial regression tests around direct and combination load paths.

Phase 2:

- Move load-combination policy into a richer `/calculate/load-combinations` API.
- Move the section recommendation engine fully server-side.
- Add API response versioning and regression fixtures against known workbook cases.

Phase 3:

- Migrate steel column checks into `core/steel/column.py`.
- Migrate timber beam checks into `core/timber/beam.py`.
- Separate EC3 and EC5 national-annex configuration.

Phase 4:

- Add plotting data endpoints.
- Add PDF and calculation report generation under `reports/`.
- Add signed calculation snapshots for auditability.

Phase 5:

- Add modules for PDF plan reading, AI-assisted beam detection, slab direction detection and wall detection.
- Keep AI outputs as proposed geometry/load inputs requiring engineer review before calculation.

## Engineering Software Practices

- Use one internal unit convention and convert explicitly at API and formula boundaries.
- Keep formulas small, named and traceable to code clauses or workbook references.
- Avoid hidden global state in calculation modules.
- Treat recommendations as engineering policy, separate from capacity checks.
- Add regression tests for every migrated workbook case before retiring the matching JavaScript path.
- Version API payloads before supporting saved project files or shared calculation links.
- Never let AI/PDF-detected loads bypass engineer review.
