from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    """Application user with role-based access."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(20), default='member', nullable=False)  # 'admin' or 'member'
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    route_assignments = relationship("RouteAssignment", back_populates="user")
    visit_logs = relationship("VisitLog", back_populates="checked_in_by_user")
    invite_codes_created = relationship("InviteCode", back_populates="created_by_user",
                                        foreign_keys="InviteCode.created_by")


class InviteCode(Base):
    """Invite codes for self-registration."""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(32), unique=True, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    used_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    created_by_user = relationship("User", foreign_keys=[created_by],
                                   back_populates="invite_codes_created")
    used_by_user = relationship("User", foreign_keys=[used_by])


class Client(Base):
    """A client/business with a vending machine location (1 Client = 1 Location)."""
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    # Location fields (merged from Location model)
    address = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    visit_logs = relationship("VisitLog", back_populates="client", cascade="all, delete-orphan")
    route_clients = relationship("RouteClient", back_populates="client")


class VisitLog(Base):
    """A visit log entry for a client location."""
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    checked_in_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="visit_logs")
    checked_in_by_user = relationship("User", back_populates="visit_logs")


class Route(Base):
    """A route containing ordered client locations."""
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    clients = relationship("RouteClient", back_populates="route", cascade="all, delete-orphan", order_by="RouteClient.position")
    assignments = relationship("RouteAssignment", back_populates="route", cascade="all, delete-orphan")


class RouteClient(Base):
    """Junction table for route-client with ordering."""
    __tablename__ = "route_clients"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    position = Column(Integer, nullable=False)

    route = relationship("Route", back_populates="clients")
    client = relationship("Client", back_populates="route_clients")


class Setting(Base):
    """Application settings stored as key-value pairs."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)  # JSON-encoded for complex values
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RouteAssignment(Base):
    """Assignment of routes to users for specific dates."""
    __tablename__ = "route_assignments"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_date = Column(Date, nullable=False)
    status = Column(String(20), default='pending', nullable=False)  # pending, in_progress, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    route = relationship("Route", back_populates="assignments")
    user = relationship("User", back_populates="route_assignments")


class RouteTemplate(Base):
    """Reusable route template that can be used to create routes quickly."""
    __tablename__ = "route_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    # Store client IDs in order as JSON array
    client_ids_json = Column(Text, nullable=False, default="[]")
    # For recurring schedules: comma-separated days (0=Mon, 1=Tue, etc) or null
    schedule_days = Column(String(20), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by_user = relationship("User")
