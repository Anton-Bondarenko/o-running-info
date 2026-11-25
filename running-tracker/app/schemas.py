from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class AthleteBase(BaseModel):
    full_name: str
    rank: Optional[str] = None
    rusada_status: bool = False
    dispensary_date: Optional[date] = None
    clinic_status: Optional[str] = "Не надо"
    is_active: bool = True


class AthleteCreate(AthleteBase):
    pass


class AthleteUpdate(BaseModel):
    full_name: Optional[str] = None
    rank: Optional[str] = None
    rusada_status: Optional[bool] = None
    dispensary_date: Optional[date] = None
    clinic_status: Optional[str] = None
    is_active: Optional[bool] = None


class AthleteResponse(AthleteBase):
    id: int

    class Config:
        from_attributes = True


class TrainingCreate(BaseModel):
    athlete_id: int
    date: date
    distance_km: float = 0.0


class TrainingUpdate(BaseModel):
    date: Optional[date] = None
    distance_km: Optional[float] = None


class TrainingResponse(BaseModel):
    id: int
    athlete_id: int
    date: date
    distance_km: float

    class Config:
        from_attributes = True


class AthleteWithTrainings(AthleteResponse):
    trainings: List[TrainingResponse] = []
