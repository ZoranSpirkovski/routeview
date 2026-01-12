import os
import json
import logging
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Query

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, date
from typing import List

from app.database import engine, get_db, Base
from app.models import VisitLog, Route, RouteClient, Client, Setting, User, InviteCode, RouteAssignment, RouteTemplate
from app.auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, get_current_admin, generate_invite_code
)

# Create tables
Base.metadata.create_all(bind=engine)

# Seed default settings and admin user
from app.database import SessionLocal
_db = SessionLocal()
try:
    from app.models import Setting as _Setting
    defaults = {
        "service_thresholds": json.dumps({"green_days": 7, "orange_days": 14}),
        "map_style": "positron"
    }
    for key, value in defaults.items():
        existing = _db.query(_Setting).filter(_Setting.key == key).first()
        if not existing:
            _db.add(_Setting(key=key, value=value))

    # Seed initial admin user if no users exist
    if _db.query(User).count() == 0:
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_user = User(
            email="admin@routeview.local",
            password_hash=get_password_hash(admin_password),
            name="Admin",
            role="admin"
        )
        _db.add(admin_user)
        print("Created initial admin user: admin@routeview.local")

    _db.commit()
finally:
    _db.close()

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


class ClientWithStatusResponse(BaseModel):
    id: int
    name: str
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    last_serviced: Optional[datetime]
    service_status: str  # "green", "orange", "red", "never"

    class Config:
        from_attributes = True


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


class SettingCreate(BaseModel):
    key: str
    value: str  # JSON string


class SettingResponse(BaseModel):
    key: str
    value: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Auth Pydantic Models ---

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    invite_code: Optional[str] = None


class UserCreateByAdmin(BaseModel):
    email: str
    password: str
    name: str
    role: str = "member"


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class InviteCodeCreate(BaseModel):
    expires_in_days: int = 7


class InviteCodeResponse(BaseModel):
    id: int
    code: str
    expires_at: datetime
    used_by: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class RouteAssignmentCreate(BaseModel):
    user_id: int
    assigned_date: str  # ISO date string YYYY-MM-DD


class RouteAssignmentResponse(BaseModel):
    id: int
    route_id: int
    user_id: int
    assigned_date: date
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RouteAssignmentWithDetailsResponse(BaseModel):
    id: int
    route_id: int
    route_name: str
    user_id: int
    user_name: str
    assigned_date: date
    status: str
    created_at: datetime


class RouteTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    client_ids: List[int] = []
    schedule_days: Optional[str] = None  # e.g., "0,2,4" for Mon, Wed, Fri


class RouteTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    client_ids: List[int]
    schedule_days: Optional[str]
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class BatchAssignmentCreate(BaseModel):
    route_id: int
    user_id: int
    dates: List[str]  # List of ISO date strings YYYY-MM-DD


class ScheduleListRequest(BaseModel):
    start_date: str  # ISO date string
    end_date: str    # ISO date string


# --- Helper Functions ---

def seed_default_settings(db: Session):
    """Seed default settings if they don't exist."""
    defaults = {
        "service_thresholds": json.dumps({"green_days": 7, "orange_days": 14}),
        "map_style": "positron"
    }
    for key, value in defaults.items():
        existing = db.query(Setting).filter(Setting.key == key).first()
        if not existing:
            db.add(Setting(key=key, value=value))
    db.commit()


def compute_service_status(last_serviced: Optional[datetime], green_days: int = 7, orange_days: int = 14) -> str:
    """Compute service status based on last serviced date."""
    if not last_serviced:
        return "never"

    days_ago = (datetime.now(last_serviced.tzinfo) - last_serviced).days

    if days_ago <= green_days:
        return "green"
    elif days_ago <= orange_days:
        return "orange"
    else:
        return "red"


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main map page."""
    return templates.TemplateResponse("index.html", {"request": request})


# --- API Endpoints ---

# --- Auth Endpoints ---

@app.post("/api/auth/register", response_model=TokenResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with an invite code."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate invite code
    if not user_data.invite_code:
        raise HTTPException(status_code=400, detail="Invite code required")

    invite = db.query(InviteCode).filter(
        InviteCode.code == user_data.invite_code,
        InviteCode.used_by == None,
        InviteCode.expires_at > datetime.now()
    ).first()

    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired invite code")

    # Create user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        name=user_data.name,
        role="member"
    )
    db.add(db_user)
    db.flush()

    # Mark invite code as used
    invite.used_by = db_user.id
    db.commit()
    db.refresh(db_user)

    # Generate token
    access_token = create_access_token(data={"sub": str(db_user.id)})
    return TokenResponse(access_token=access_token, user=db_user)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login with email and password."""
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")

    access_token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(access_token=access_token, user=user)


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user's profile."""
    return current_user


# --- User Management Endpoints (Admin Only) ---

@app.get("/api/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all users (admin only)."""
    return db.query(User).order_by(User.created_at.desc()).all()


@app.post("/api/users", response_model=UserResponse)
def create_user(
    user_data: UserCreateByAdmin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Create a user directly (admin only)."""
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        name=user_data.name,
        role=user_data.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.put("/api/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Update a user (admin only)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_data.name is not None:
        db_user.name = user_data.name
    if user_data.role is not None:
        db_user.role = user_data.role
    if user_data.is_active is not None:
        db_user.is_active = user_data.is_active

    db.commit()
    db.refresh(db_user)
    return db_user


@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Deactivate a user (admin only). Does not delete to preserve history."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.is_active = False
    db.commit()
    return {"message": "User deactivated"}


# --- Invite Code Endpoints (Admin Only) ---

@app.post("/api/invite-codes", response_model=InviteCodeResponse)
def create_invite_code(
    data: InviteCodeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Generate a new invite code (admin only)."""
    code = generate_invite_code()
    expires_at = datetime.now() + timedelta(days=data.expires_in_days)

    db_invite = InviteCode(
        code=code,
        created_by=current_user.id,
        expires_at=expires_at
    )
    db.add(db_invite)
    db.commit()
    db.refresh(db_invite)
    return db_invite


@app.get("/api/invite-codes", response_model=List[InviteCodeResponse])
def list_invite_codes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all invite codes (admin only)."""
    return db.query(InviteCode).order_by(InviteCode.created_at.desc()).all()


@app.delete("/api/invite-codes/{code_id}")
def delete_invite_code(
    code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete an unused invite code (admin only)."""
    invite = db.query(InviteCode).filter(InviteCode.id == code_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite code not found")
    if invite.used_by:
        raise HTTPException(status_code=400, detail="Cannot delete used invite code")

    db.delete(invite)
    db.commit()
    return {"message": "Invite code deleted"}


# --- Route Assignment Endpoints ---

@app.post("/api/routes/{route_id}/assign", response_model=RouteAssignmentResponse)
def assign_route(
    route_id: int,
    assignment: RouteAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a route to a user for a specific date (admin only)."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    user = db.query(User).filter(User.id == assignment.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assigned_date = datetime.strptime(assignment.assigned_date, "%Y-%m-%d").date()

    # Check for existing assignment
    existing = db.query(RouteAssignment).filter(
        RouteAssignment.route_id == route_id,
        RouteAssignment.user_id == assignment.user_id,
        RouteAssignment.assigned_date == assigned_date
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Route already assigned to this user for this date")

    db_assignment = RouteAssignment(
        route_id=route_id,
        user_id=assignment.user_id,
        assigned_date=assigned_date
    )
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment


@app.get("/api/my-routes", response_model=List[RouteAssignmentResponse])
def get_my_routes(
    date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get routes assigned to current user."""
    query = db.query(RouteAssignment).filter(RouteAssignment.user_id == current_user.id)

    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        query = query.filter(RouteAssignment.assigned_date == target_date)
    else:
        # Default to today
        query = query.filter(RouteAssignment.assigned_date == datetime.now().date())

    return query.order_by(RouteAssignment.assigned_date.desc()).all()


@app.put("/api/route-assignments/{assignment_id}/status")
def update_assignment_status(
    assignment_id: int,
    status: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update route assignment status (owner or admin)."""
    assignment = db.query(RouteAssignment).filter(RouteAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Check permission
    if assignment.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if status not in ["pending", "in_progress", "completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    assignment.status = status
    db.commit()
    return {"message": "Status updated"}


@app.delete("/api/route-assignments/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Delete a route assignment (admin only)."""
    assignment = db.query(RouteAssignment).filter(RouteAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    return {"message": "Assignment deleted"}


@app.get("/api/schedule")
def get_schedule(
    start_date: str = Query(...),
    end_date: str = Query(...),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all route assignments within a date range (admin sees all, members see their own)."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    query = db.query(RouteAssignment).filter(
        RouteAssignment.assigned_date >= start,
        RouteAssignment.assigned_date <= end
    )

    # Non-admins can only see their own assignments
    if current_user.role != "admin":
        query = query.filter(RouteAssignment.user_id == current_user.id)
    elif user_id:
        query = query.filter(RouteAssignment.user_id == user_id)

    assignments = query.order_by(RouteAssignment.assigned_date).all()

    # Build response with route and user details
    result = []
    for a in assignments:
        result.append({
            "id": a.id,
            "route_id": a.route_id,
            "route_name": a.route.name if a.route else "Unknown",
            "user_id": a.user_id,
            "user_name": a.user.name if a.user else "Unknown",
            "assigned_date": a.assigned_date.isoformat(),
            "status": a.status,
            "created_at": a.created_at.isoformat() if a.created_at else None
        })

    return result


@app.post("/api/schedule/batch")
def batch_assign_routes(
    data: BatchAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Batch assign a route to a user for multiple dates (admin only)."""
    route = db.query(Route).filter(Route.id == data.route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    user = db.query(User).filter(User.id == data.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    created = 0
    skipped = 0

    for date_str in data.dates:
        assigned_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Check for existing assignment
        existing = db.query(RouteAssignment).filter(
            RouteAssignment.route_id == data.route_id,
            RouteAssignment.user_id == data.user_id,
            RouteAssignment.assigned_date == assigned_date
        ).first()

        if existing:
            skipped += 1
            continue

        db_assignment = RouteAssignment(
            route_id=data.route_id,
            user_id=data.user_id,
            assigned_date=assigned_date
        )
        db.add(db_assignment)
        created += 1

    db.commit()
    return {"message": f"Created {created} assignments, skipped {skipped} duplicates"}


# --- Route Template Endpoints ---

@app.get("/api/route-templates")
def list_route_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all route templates."""
    templates = db.query(RouteTemplate).order_by(RouteTemplate.created_at.desc()).all()
    result = []
    for t in templates:
        client_ids = json.loads(t.client_ids_json) if t.client_ids_json else []
        result.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "client_ids": client_ids,
            "client_count": len(client_ids),
            "schedule_days": t.schedule_days,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None
        })
    return result


@app.post("/api/route-templates")
def create_route_template(
    template: RouteTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new route template."""
    # Validate client IDs exist
    for client_id in template.client_ids:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=400, detail=f"Client {client_id} not found")

    db_template = RouteTemplate(
        name=template.name,
        description=template.description,
        client_ids_json=json.dumps(template.client_ids),
        schedule_days=template.schedule_days,
        created_by=current_user.id
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    return {
        "id": db_template.id,
        "name": db_template.name,
        "description": db_template.description,
        "client_ids": template.client_ids,
        "schedule_days": db_template.schedule_days,
        "created_by": db_template.created_by,
        "created_at": db_template.created_at.isoformat() if db_template.created_at else None
    }


@app.get("/api/route-templates/{template_id}")
def get_route_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single route template with client details."""
    template = db.query(RouteTemplate).filter(RouteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    client_ids = json.loads(template.client_ids_json) if template.client_ids_json else []

    # Get client details in order
    clients = []
    for client_id in client_ids:
        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            clients.append({
                "id": client.id,
                "name": client.name,
                "address": client.address,
                "latitude": client.latitude,
                "longitude": client.longitude
            })

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "client_ids": client_ids,
        "clients": clients,
        "schedule_days": template.schedule_days,
        "created_by": template.created_by,
        "created_at": template.created_at.isoformat() if template.created_at else None
    }


@app.put("/api/route-templates/{template_id}")
def update_route_template(
    template_id: int,
    template_data: RouteTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a route template."""
    template = db.query(RouteTemplate).filter(RouteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Only creator or admin can update
    if template.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Validate client IDs exist
    for client_id in template_data.client_ids:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(status_code=400, detail=f"Client {client_id} not found")

    template.name = template_data.name
    template.description = template_data.description
    template.client_ids_json = json.dumps(template_data.client_ids)
    template.schedule_days = template_data.schedule_days

    db.commit()
    db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "client_ids": template_data.client_ids,
        "schedule_days": template.schedule_days,
        "created_by": template.created_by,
        "created_at": template.created_at.isoformat() if template.created_at else None
    }


@app.delete("/api/route-templates/{template_id}")
def delete_route_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a route template."""
    template = db.query(RouteTemplate).filter(RouteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Only creator or admin can delete
    if template.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    db.delete(template)
    db.commit()
    return {"message": "Template deleted"}


@app.post("/api/route-templates/{template_id}/create-route")
def create_route_from_template(
    template_id: int,
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new route from a template."""
    template = db.query(RouteTemplate).filter(RouteTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    client_ids = json.loads(template.client_ids_json) if template.client_ids_json else []

    # Create the route with optional custom name
    route_name = name if name else f"{template.name} - {datetime.now().strftime('%Y-%m-%d')}"
    db_route = Route(name=route_name, description=template.description)
    db.add(db_route)
    db.flush()

    # Add clients to route in order
    for idx, client_id in enumerate(client_ids):
        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            route_client = RouteClient(route_id=db_route.id, client_id=client_id, position=idx)
            db.add(route_client)

    db.commit()
    db.refresh(db_route)

    return {
        "id": db_route.id,
        "name": db_route.name,
        "description": db_route.description,
        "client_count": len(client_ids)
    }


@app.post("/api/routes/{route_id}/save-as-template")
def save_route_as_template(
    route_id: int,
    name: Optional[str] = Query(None),
    schedule_days: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save an existing route as a template."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    # Get client IDs in order
    client_ids = [rc.client_id for rc in sorted(route.clients, key=lambda x: x.position)]

    # Create template
    template_name = name if name else f"{route.name} Template"
    db_template = RouteTemplate(
        name=template_name,
        description=route.description,
        client_ids_json=json.dumps(client_ids),
        schedule_days=schedule_days,
        created_by=current_user.id
    )
    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    return {
        "id": db_template.id,
        "name": db_template.name,
        "description": db_template.description,
        "client_ids": client_ids,
        "schedule_days": db_template.schedule_days,
        "created_by": db_template.created_by,
        "created_at": db_template.created_at.isoformat() if db_template.created_at else None
    }


# --- Client Endpoints (Primary API) ---

@app.get("/api/clients", response_model=list[ClientResponse])
def get_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all clients (each client = one location)."""
    return db.query(Client).all()


@app.get("/api/clients/with-status", response_model=list[ClientWithStatusResponse])
def get_clients_with_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all clients with last serviced date and service status."""
    from sqlalchemy import func

    # Subquery to get latest visit per client
    latest_visit = db.query(
        VisitLog.client_id,
        func.max(VisitLog.created_at).label('last_serviced')
    ).group_by(VisitLog.client_id).subquery()

    # Join clients with latest visit
    results = db.query(
        Client,
        latest_visit.c.last_serviced
    ).outerjoin(
        latest_visit,
        Client.id == latest_visit.c.client_id
    ).all()

    # Try to load thresholds from settings, use defaults if not available
    try:
        setting = db.query(Setting).filter(Setting.key == "service_thresholds").first()
        if setting:
            thresholds = json.loads(setting.value)
            green_days = thresholds.get("green_days", 7)
            orange_days = thresholds.get("orange_days", 14)
        else:
            green_days, orange_days = 7, 14
    except:
        green_days, orange_days = 7, 14

    # Build response
    response = []
    for client, last_serviced in results:
        status = compute_service_status(last_serviced, green_days, orange_days)
        response.append(ClientWithStatusResponse(
            id=client.id,
            name=client.name,
            address=client.address,
            latitude=client.latitude,
            longitude=client.longitude,
            contact_name=client.contact_name,
            contact_phone=client.contact_phone,
            contact_email=client.contact_email,
            notes=client.notes,
            last_serviced=last_serviced,
            service_status=status
        ))

    return response


@app.post("/api/clients", response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new client with location."""
    try:
        logger.info(f"Creating client: name='{client.name}', user_id={current_user.id}")
        db_client = Client(**client.model_dump())
        db.add(db_client)
        db.commit()
        db.refresh(db_client)
        logger.info(f"Client created successfully: id={db_client.id}, name='{db_client.name}'")
        return db_client
    except Exception as e:
        logger.error(f"Failed to create client: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create client: {str(e)}")


@app.get("/api/clients/{client_id}", response_model=ClientResponse)
def get_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a single client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.put("/api/clients/{client_id}", response_model=ClientResponse)
def update_client(client_id: int, client: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Update a client."""
    try:
        logger.info(f"Updating client: id={client_id}, user_id={current_user.id}")
        db_client = db.query(Client).filter(Client.id == client_id).first()
        if not db_client:
            logger.warning(f"Client not found for update: id={client_id}")
            raise HTTPException(status_code=404, detail="Client not found")

        for key, value in client.model_dump().items():
            setattr(db_client, key, value)

        db.commit()
        db.refresh(db_client)
        logger.info(f"Client updated successfully: id={db_client.id}")
        return db_client
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update client {client_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update client: {str(e)}")


@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Delete a client and all associated data (admin only)."""
    try:
        logger.info(f"Deleting client: id={client_id}, admin_id={current_user.id}")
        db_client = db.query(Client).filter(Client.id == client_id).first()
        if not db_client:
            logger.warning(f"Client not found for deletion: id={client_id}")
            raise HTTPException(status_code=404, detail="Client not found")

        client_name = db_client.name
        # Remove from any routes
        db.query(RouteClient).filter(RouteClient.client_id == client_id).delete()

        db.delete(db_client)
        db.commit()
        logger.info(f"Client deleted successfully: id={client_id}, name='{client_name}'")
        return {"message": "Client deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete client {client_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete client: {str(e)}")


# --- Location Endpoints (Backward Compatibility Alias) ---

@app.get("/api/locations", response_model=list[LocationResponse])
def get_locations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all locations (alias for clients - backward compatibility)."""
    return db.query(Client).all()


@app.post("/api/locations", response_model=LocationResponse)
def create_location(location: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a new location (alias for client creation - backward compatibility)."""
    db_client = Client(**location.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


@app.get("/api/locations/{location_id}", response_model=LocationResponse)
def get_location(location_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a single location (alias for client - backward compatibility)."""
    client = db.query(Client).filter(Client.id == location_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Location not found")
    return client


@app.put("/api/locations/{location_id}", response_model=LocationResponse)
def update_location(location_id: int, location: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def delete_location(location_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Delete a location (alias for client deletion - backward compatibility, admin only)."""
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
def get_client_visit_logs(client_id: int, search: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all visit logs for a client, newest first."""
    query = db.query(VisitLog).filter(VisitLog.client_id == client_id)
    if search:
        query = query.filter(
            (VisitLog.title.ilike(f"%{search}%")) |
            (VisitLog.notes.ilike(f"%{search}%"))
        )
    return query.order_by(VisitLog.created_at.desc()).all()


@app.post("/api/clients/{client_id}/logs", response_model=VisitLogResponse)
def create_client_visit_log(client_id: int, log: VisitLogCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
        notes=log.notes,
        checked_in_by=current_user.id
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


# Backward compatibility endpoints for visit logs using location_id
@app.get("/api/locations/{location_id}/logs", response_model=list[VisitLogResponse])
def get_visit_logs(location_id: int, search: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all visit logs for a location (alias for client - backward compatibility)."""
    return get_client_visit_logs(location_id, search, db, current_user)


@app.post("/api/locations/{location_id}/logs", response_model=VisitLogResponse)
def create_visit_log(location_id: int, log: VisitLogCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a visit log entry (alias for client - backward compatibility)."""
    return create_client_visit_log(location_id, log, db, current_user)


@app.delete("/api/logs/{log_id}")
def delete_visit_log(log_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Delete a visit log entry (admin only)."""
    db_log = db.query(VisitLog).filter(VisitLog.id == log_id).first()
    if not db_log:
        raise HTTPException(status_code=404, detail="Log not found")

    db.delete(db_log)
    db.commit()
    return {"message": "Log deleted"}


# --- Route Endpoints ---

@app.get("/api/routes")
def get_routes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def create_route(route: RouteCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def get_route(route_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a single route with all clients."""
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@app.put("/api/routes/{route_id}", response_model=RouteResponse)
def update_route(route_id: int, route: RouteCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def delete_route(route_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Delete a route (admin only)."""
    db_route = db.query(Route).filter(Route.id == route_id).first()
    if not db_route:
        raise HTTPException(status_code=404, detail="Route not found")

    db.delete(db_route)
    db.commit()
    return {"message": "Route deleted"}


# --- Settings Endpoints ---

@app.get("/api/settings")
def get_all_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get all settings as a dictionary."""
    settings = db.query(Setting).all()
    return {s.key: s.value for s in settings}


@app.get("/api/settings/{key}", response_model=SettingResponse)
def get_setting(key: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get a specific setting by key."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@app.put("/api/settings/{key}", response_model=SettingResponse)
def update_setting(key: str, setting: SettingCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    """Update or create a setting (upsert). Admin only."""
    db_setting = db.query(Setting).filter(Setting.key == key).first()
    if db_setting:
        db_setting.value = setting.value
    else:
        db_setting = Setting(key=key, value=setting.value)
        db.add(db_setting)
    db.commit()
    db.refresh(db_setting)
    return db_setting
