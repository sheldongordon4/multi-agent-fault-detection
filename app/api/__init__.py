from .main import app
from fastapi import FastAPI

from app.api.routes.faults import router as faults_router

app = FastAPI(title="MAFD API")

# Include the faults router so /faults/diagnose exists
app.include_router(faults_router)
