"""UI Router for serving HTML pages."""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(include_in_schema=False)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@router.get("/")
async def home(request: Request):
    """Render the main UI dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})
