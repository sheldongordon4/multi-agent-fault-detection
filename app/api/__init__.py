# app/api/__init__.py
from .main import app  # or from ..main import app, depending on where it is

from fastapi import FastAPI

from app.api.routes.faults import router as faults_router

app = FastAPI(title="MAFD API")

# Include the faults router so /faults/diagnose exists
app.include_router(faults_router)
