@echo off

IF NOT EXIST .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate

pip install -r requirements.txt

start http://127.0.0.1:8000

uvicorn app:app --reload

pause