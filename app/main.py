import os
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import engine, get_db, Base
from app.models import VisitLog, Route, RouteClient, Client
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


# --- Pydantic Models ---

class ClientCreate(BaseModel):
    name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    # Location fields
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class ClientResponse(BaseModel):
    id: int
    name: str
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    # Location fields
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]

    class Config:
        from_attributes = True


# Backward compatibility alias for location responses
class LocationResponse(BaseModel):
    """Alias for ClientResponse for backward compatibility with /api/locations endpoint."""
    id: int
    name: str
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    notes: Optional[str]
    # Include client fields for full compatibility
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    class Config:
        from_attributes = True


class VisitLogCreate(BaseModel):
    notes: Optional[str] = None


class VisitLogResponse(BaseModel):
    id: int
    client_id: int
    title: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RouteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    client_ids: List[int] = []


class RouteClientResponse(BaseModel):
    id: int
    client_id: int
    position: int
    client: ClientResponse

    class Config:
        from_attributes = True


class RouteResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    clients: List[RouteClientResponse] = []

    class Config:
        from_attributes = True


class RouteListResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    client_count: int

    class Config:
        from_attributes = True


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main map page."""
    return templates.TemplateResponse("index.html", {"request": request})


# --- API Endpoints ---

# --- Client Endpoints (Primary API) ---

@app.get("/api/clients", response_model=list[ClientResponse])
def get_clients(db: Session = Depends(get_db)):
    """Get all clients (each client = one location)."""
    return db.query(Client).all()


@app.post("/api/clients", response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    """Create a new client with location."""
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
    """Delete a client and all associated data."""
    db_client = db.query(Client).filter(Client.id == client_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Remove from any routes
    db.query(RouteClient).filter(RouteClient.client_id == client_id).delete()

    db.delete(db_client)
    db.commit()
    return {"message": "Client deleted"}


# --- Location Endpoints (Backward Compatibility Alias) ---

@app.get("/api/locations", response_model=list[LocationResponse])
def get_locations(db: Session = Depends(get_db)):
    """Get all locations (alias for clients - backward compatibility)."""
    return db.query(Client).all()


@app.post("/api/locations", response_model=LocationResponse)
def create_location(location: ClientCreate, db: Session = Depends(get_db)):
    """Create a new location (alias for client creation - backward compatibility)."""
    db_client = Client(**location.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@app.get("/api/locations/{location_id}", response_model=LocationResponse)
def get_location(location_id: int, db: Session = Depends(get_db)):
    """Get a single location (alias for client - backward compatibility)."""
    client = db.query(Client).filter(Client.id == location_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Location not found")
    return client


@app.put("/api/locations/{location_id}", response_model=LocationResponse)
def update_location(location_id: int, location: ClientCreate, db: Session = Depends(get_db)):
    """Update a location (alias for client update - backward compatibility)."""
    db_client = db.query(Client).filter(Client.id == location_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Location not found")

    for key, value in location.model_dump().items():
        setattr(db_client, key, value)

    db.commit()
    db.refresh(db_client)
    return db_client


@app.delete("/api/locations/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db)):
    """Delete a location (alias for client deletion - backward compatibility)."""
    db_client = db.query(Client).filter(Client.id == location_id).first()
    if not db_client:
        raise HTTPException(status_code=404, detail="Location not found")

    # Remove from any routes
    db.query(RouteClient).filter(RouteClient.client_id == location_id).delete()

    db.delete(db_client)
    db.commit()
    return {"message": "Location deleted"}


@app.get("/health")
def health_check():
    """Health check endpoint for deployment."""
    return {"status": "healthy"}


# --- Visit Log Endpoints ---

@app.get("/api/clients/{client_id}/logs", response_model=list[VisitLogResponse])
def get_client_visit_logs(client_id: int, search: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all visit logs for a client, newest first."""
    query = db.query(VisitLog).filter(VisitLog.client_id == client_id)
    if search:
        query = query.filter(
            (VisitLog.title.ilike(f"%{search}%")) |
            (VisitLog.notes.ilike(f"%{search}%"))
        )
    return query.order_by(VisitLog.created_at.desc()).all()


@app.post("/api/clients/{client_id}/logs", response_model=VisitLogResponse)
def create_client_visit_log(client_id: int, log: VisitLogCreate, db: Session = Depends(get_db)):
    """Create a visit log entry for a client with auto-generated title."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Auto-generate title: "Visit - Jan 10, 2026 6:30 PM"
    now = datetime.now()
    title = f"Visit - {now.strftime('%b %d, %Y %I:%M %p')}"

    db_log = VisitLog(
        client_id=client_id,
        title=title,
        notes=log.notes
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


# Backward compatibility endpoints for visit logs using location_id
@app.get("/api/locations/{location_id}/logs", response_model=list[VisitLogResponse])
def get_visit_logs(location_id: int, search: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all visit logs for a location (alias for client - backward compatibility)."""
    return get_client_visit_logs(location_id, search, db)


@app.post("/api/locations/{location_id}/logs", response_model=VisitLogResponse)
def create_visit_log(location_id: int, log: VisitLogCreate, db: Session = Depends(get_db)):
    """Create a visit log entry (alias for client - backward compatibility)."""
    return create_client_visit_log(location_id, log, db)


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
    """Get all routes with client count."""
    routes = db.query(Route).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "client_count": len(r.clients),
            # Backward compatibility
            "location_count": len(r.clients)
        }
        for r in routes
    ]


@app.post("/api/routes", response_model=RouteResponse)
def create_route(route: RouteCreate, db: Session = Depends(get_db)):
    """Create a new route with clients."""
    db_route = Route(name=route.name, description=route.description)
    db.add(db_route)
    db.flush()

    for idx, client_id in enumerate(route.client_ids):
        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            route_client = RouteClient(route_id=db_route.id, client_id=client_id, position=idx)
            db.add(route_client)

    db.commit()
    db.refresh(db_route)
    return db_route


@app.get("/api/routes/{route_id}", response_model=RouteResponse)
def get_route(route_id: int, db: Session = Depends(get_db)):
    """Get a single route with all clients."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.put("/api/routes/{route_id}", response_model=RouteResponse)
def update_route(route_id: int, route: RouteCreate, db: Session = Depends(get_db)):
    """Update a route and its clients."""
    db_route = db.query(Route).filter(Route.id == route_id).first()
    if not db_route:
        raise HTTPException(status_code=404, detail="Route not found")

    db_route.name = route.name
    db_route.description = route.description

    # Clear existing clients and re-add
    db.query(RouteClient).filter(RouteClient.route_id == route_id).delete()

    for idx, client_id in enumerate(route.client_ids):
        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            route_client = RouteClient(route_id=route_id, client_id=client_id, position=idx)
            db.add(route_client)

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
