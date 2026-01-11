import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import engine, get_db, Base
from app.models import Location, VisitLog, Route, RouteLocation, Client
from datetime import datetime
from typing import List

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RouteView", description="Vending machine location tracker")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Simple password protection (set via environment variable)
APP_PASSWORD = os.getenv("ROUTEVIEW_PASSWORD", "demo123")


class ClientCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class ClientResponse(BaseModel):
    id: int
    name: str
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


class LocationCreate(BaseModel):
    name: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    notes: Optional[str] = None
    client_id: Optional[int] = None


class LocationResponse(BaseModel):
    id: int
    name: str
    address: Optional[str]
    latitude: float
    longitude: float
    notes: Optional[str]
    client_id: Optional[int]
    client: Optional[ClientResponse] = None

    class Config:
        from_attributes = True


class VisitLogCreate(BaseModel):
    notes: Optional[str] = None


class VisitLogResponse(BaseModel):
    id: int
    location_id: int
    title: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RouteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    location_ids: List[int] = []


class RouteLocationResponse(BaseModel):
    id: int
    location_id: int
    position: int
    location: LocationResponse

    class Config:
        from_attributes = True


class RouteResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    locations: List[RouteLocationResponse] = []

    class Config:
        from_attributes = True


class RouteListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    location_count: int

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


# --- Visit Log Endpoints ---

@app.get("/api/locations/{location_id}/logs", response_model=list[VisitLogResponse])
def get_visit_logs(location_id: int, search: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all visit logs for a location, newest first."""
    query = db.query(VisitLog).filter(VisitLog.location_id == location_id)
    if search:
        query = query.filter(
            (VisitLog.title.ilike(f"%{search}%")) |
            (VisitLog.notes.ilike(f"%{search}%"))
        )
    return query.order_by(VisitLog.created_at.desc()).all()


@app.post("/api/locations/{location_id}/logs", response_model=VisitLogResponse)
def create_visit_log(location_id: int, log: VisitLogCreate, db: Session = Depends(get_db)):
    """Create a visit log entry with auto-generated title."""
    location = db.query(Location).filter(Location.id == location_id).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Auto-generate title: "Visit - Jan 10, 2026 6:30 PM"
    now = datetime.now()
    title = f"Visit - {now.strftime('%b %d, %Y %I:%M %p')}"

    db_log = VisitLog(
        location_id=location_id,
        title=title,
        notes=log.notes
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


@app.delete("/api/logs/{log_id}")
def delete_visit_log(log_id: int, db: Session = Depends(get_db)):
    """Delete a visit log entry."""
    db_log = db.query(VisitLog).filter(VisitLog.id == log_id).first()
    if not db_log:
        raise HTTPException(status_code=404, detail="Log not found")

    db.delete(db_log)
    db.commit()
    return {"message": "Log deleted"}


# --- Route Endpoints ---

@app.get("/api/routes")
def get_routes(db: Session = Depends(get_db)):
    """Get all routes with location count."""
    routes = db.query(Route).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "location_count": len(r.locations)
        }
        for r in routes
    ]


@app.post("/api/routes", response_model=RouteResponse)
def create_route(route: RouteCreate, db: Session = Depends(get_db)):
    """Create a new route with locations."""
    db_route = Route(name=route.name, description=route.description)
    db.add(db_route)
    db.flush()

    for idx, loc_id in enumerate(route.location_ids):
        location = db.query(Location).filter(Location.id == loc_id).first()
        if location:
            route_loc = RouteLocation(route_id=db_route.id, location_id=loc_id, position=idx)
            db.add(route_loc)

    db.commit()
    db.refresh(db_route)
    return db_route


@app.get("/api/routes/{route_id}", response_model=RouteResponse)
def get_route(route_id: int, db: Session = Depends(get_db)):
    """Get a single route with all locations."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.put("/api/routes/{route_id}", response_model=RouteResponse)
def update_route(route_id: int, route: RouteCreate, db: Session = Depends(get_db)):
    """Update a route and its locations."""
    db_route = db.query(Route).filter(Route.id == route_id).first()
    if not db_route:
        raise HTTPException(status_code=404, detail="Route not found")

    db_route.name = route.name
    db_route.description = route.description

    # Clear existing locations and re-add
    db.query(RouteLocation).filter(RouteLocation.route_id == route_id).delete()

    for idx, loc_id in enumerate(route.location_ids):
        location = db.query(Location).filter(Location.id == loc_id).first()
        if location:
            route_loc = RouteLocation(route_id=route_id, location_id=loc_id, position=idx)
            db.add(route_loc)

    db.commit()
    db.refresh(db_route)
    return db_route


@app.delete("/api/routes/{route_id}")
def delete_route(route_id: int, db: Session = Depends(get_db)):
    """Delete a route."""
    db_route = db.query(Route).filter(Route.id == route_id).first()
    if not db_route:
        raise HTTPException(status_code=404, detail="Route not found")

    db.delete(db_route)
    db.commit()
    return {"message": "Route deleted"}


# --- Client Endpoints ---

@app.get("/api/clients")
def get_clients(db: Session = Depends(get_db)):
    """Get all clients with location count."""
    clients = db.query(Client).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "contact_name": c.contact_name,
            "contact_phone": c.contact_phone,
            "contact_email": c.contact_email,
            "notes": c.notes,
            "location_count": len(c.locations)
        }
        for c in clients
    ]


@app.post("/api/clients", response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    """Create a new client."""
    db_client = Client(**client.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@app.get("/api/clients/{client_id}", response_model=ClientResponse)
def get_client(client_id: int, db: Session = Depends(get_db)):
    """Get a single client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.put("/api/clients/{client_id}", response_model=ClientResponse)
def update_client(client_id: int, client: ClientCreate, db: Session = Depends(get_db)):
    """Update a client."""
    db_client = db.query(Client).filter(Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    for key, value in client.model_dump().items():
        setattr(db_client, key, value)

    db.commit()
    db.refresh(db_client)
    return db_client


@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    """Delete a client."""
    db_client = db.query(Client).filter(Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Unlink locations (set client_id to null instead of deleting)
    db.query(Location).filter(Location.client_id == client_id).update({"client_id": None})

    db.delete(db_client)
    db.commit()
    return {"message": "Client deleted"}
