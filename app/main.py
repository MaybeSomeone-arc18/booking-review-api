from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.routers import auth, bookings, reviews

STATIC = Path(__file__).parent / "static"

app = FastAPI(
    title="Service Booking & Review API",
    description="Providers offer slots, customers book them, completed bookings get reviewed.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(bookings.router)
app.include_router(reviews.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def ui():
    return FileResponse(STATIC / "index.html")
