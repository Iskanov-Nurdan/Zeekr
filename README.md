# Zeekr Backend

Plain Django backend for the Zeekr halal-check service, covering stage 1 and stage 2 from the specification.

## Included

- Product, ingredient, brand, boycott, history, favorites, and complaint models
- Search pages with classic Django views and templates
- OCR upload flow for ingredient photos
- Heuristic halal/haram/doubtful classification engine
- Optional OpenAI explanation layer
- Optional PostgreSQL, Redis, and Celery settings via `.env`
- Django admin for reference data and moderation

## Quick start

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

## Important notes

- The project runs on SQLite by default and switches to PostgreSQL when `POSTGRES_DB` is set.
- OCR uses `pytesseract`; set `TESSERACT_CMD` in `.env` if Tesseract is installed outside PATH.
- OpenAI explanations are optional; without `OPENAI_API_KEY`, the app uses local summary logic.
- External product source syncing is prepared via `ExternalProductCache`, but provider adapters still need to be connected in the next step.
