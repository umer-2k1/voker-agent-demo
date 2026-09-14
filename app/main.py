import os

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "Voker Agent API"),
    version="0.1.0",
)


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {"message": "Voker Agent API is running"}


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "environment": os.getenv("APP_ENV", "development")}
