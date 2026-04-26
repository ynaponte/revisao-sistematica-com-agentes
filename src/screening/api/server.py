"""Main API server application."""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .routes.screening import router as screening_router
from ..ui.router import router as ui_router

load_dotenv()

app = FastAPI(title="Screening API", description="API for Systematic Review Screening Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screening_router)
app.include_router(ui_router)

def main():
    uvicorn.run("screening.api.server:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
