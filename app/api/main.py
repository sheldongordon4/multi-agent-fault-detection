from fastapi import FastAPI

app = FastAPI(title="MAFD MVP")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
