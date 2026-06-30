from fastapi import FastAPI

from app.api.routes.faults import router as faults_router

app = FastAPI(title="MAFD MVP")

app.include_router(faults_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
