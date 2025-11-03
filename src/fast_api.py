import uvicorn
from fastapi import FastAPI

from src.endpoints.match_endpoints import router as match_router

app = FastAPI(title="Match Worker Service", version="0.1.0")
app.include_router(match_router, prefix="/api/v0", tags=["match"])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)