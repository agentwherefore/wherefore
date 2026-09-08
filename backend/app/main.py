from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .database import Base, engine
from .routers import claude_cli_auth, extraction, projects, uploads
from .seed import seed_canonical_project

STATIC_DIR = Path(__file__).resolve().parent / "static"

Base.metadata.create_all(bind=engine)
seed_canonical_project()

app = FastAPI(title="Wherefore")

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(uploads.router, prefix="/api/projects", tags=["uploads"])
app.include_router(extraction.router, prefix="/api/projects", tags=["extraction"])
app.include_router(claude_cli_auth.router, prefix="/api/settings", tags=["settings"])


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
