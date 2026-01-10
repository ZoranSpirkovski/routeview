from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Location(Base):
    """A vending machine location."""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(255), nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    visit_logs = relationship("VisitLog", back_populates="location", cascade="all, delete-orphan")


class VisitLog(Base):
    """A visit log entry for a location."""
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    title = Column(String(200), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    location = relationship("Location", back_populates="visit_logs")


class Route(Base):
    """A route containing ordered locations."""
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    locations = relationship("RouteLocation", back_populates="route", cascade="all, delete-orphan", order_by="RouteLocation.position")


class RouteLocation(Base):
    """Junction table for route-location with ordering."""
    __tablename__ = "route_locations"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    position = Column(Integer, nullable=False)

    route = relationship("Route", back_populates="locations")
    location = relationship("Location")
