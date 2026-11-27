from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Date,
    Float,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.database import Base


def calculate_dispensary_status(dispensary_date: Optional[date]) -> str:
    """Расчет статуса справки диспансера относительно текущей даты."""
    if dispensary_date is None:
        return "none"
    today = date.today()
    delta = dispensary_date - today
    if delta.days <= 14:
        return "expired"
    return "valid"


class Athlete(Base):
    __tablename__ = "athletes"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    rank = Column(String, nullable=True)
    rusada_status = Column(Boolean, default=False)
    dispensary_date = Column(Date, nullable=True)
    clinic_status = Column(String, default="Не надо")
    xp = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    test_field = Column(String, nullable=True)  # test field for migration check

    trainings = relationship("Training", back_populates="athlete", cascade="all, delete-orphan")

    def calculate_dispensary_status(self) -> str:
        return calculate_dispensary_status(self.dispensary_date)


class Training(Base):
    __tablename__ = "trainings"

    id = Column(Integer, primary_key=True, index=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"))
    date = Column(Date, nullable=False)
    distance_km = Column(Float, default=0.0)

    athlete = relationship("Athlete", back_populates="trainings")
