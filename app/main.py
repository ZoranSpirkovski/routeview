import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import engine, get_db, Base
from app.models import Location

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RouteView", description="Vending machine location tracker")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Simple password protection (set via environment variable)
APP_PASSWORD = os.getenv("ROUTEVIEW_PASSWORD", "demo123")


class LocationCreate(BaseModel):
    name: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    notes: Optional[str] = None


class LocationResponse(BaseModel):
    id: int
    name: str
    address: Optional[str]
    latitude: float
    longitude: float
    notes: Optional[str]

    class Config:
        from_attributes = True


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main map page."""
    return templates.TemplateResponse("index.html", {"request": request})


# --- API Endpoints ---

@app.get("/api/locations", response_model=list[LocationResponse])
def get_locations(db: Session = Depends(get_db)):
    """Get all locations."""
    return db.query(Location).all()


@app.post("/api/locations", response_model=LocationResponse)
def create_location(location: LocationCreate, db: Session = Depends(get_db)):
    """Create a new location."""
    db_location = Location(**location.model_dump())
    db.add(db_location)
    db.commit()
    db.refresh(db_location)
    return db_location


@app.get("/api/locations/{location_id}", response_model=LocationResponse)
def get_location(location_id: int, db: Session = Depends(get_db)):
    """Get a single location."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


@app.put("/api/locations/{location_id}", response_model=LocationResponse)
def update_location(location_id: int, location: LocationCreate, db: Session = Depends(get_db)):
    """Update a location."""
    db_location = db.query(Location).filter(Location.id == location_id).first()
    if not db_location:
        raise HTTPException(status_code=404, detail="Location not found")

    for key, value in location.model_dump().items():
        setattr(db_location, key, value)

    db.commit()
    db.refresh(db_location)
    return db_location


@app.delete("/api/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    """Delete a location."""
    db_location = db.query(Location).filter(Location.id == location_id).first()
    if not db_location:
        raise HTTPException(status_code=404, detail="Location not found")

    db.delete(db_location)
    db.commit()
    return {"message": "Location deleted"}


@app.get("/health")
def health_check():
    """Health check endpoint for deployment."""
    return {"status": "healthy"}
