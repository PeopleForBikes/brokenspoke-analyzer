"""Define the database models."""

from sqlalchemy import (
    CHAR,
    SmallInteger,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


class StateSpeed(Base):
    __tablename__ = "state_speed"

    state: Mapped[str] = mapped_column(CHAR(2))
    fips_code_state: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    speed: Mapped[int] = mapped_column(SmallInteger)


class CitySpeed(Base):
    __tablename__ = "city_speed"

    city: Mapped[str]
    state: Mapped[str] = mapped_column(CHAR(2))
    fips_code_city: Mapped[str] = mapped_column(CHAR(7), primary_key=True)
    speed: Mapped[int] = mapped_column(SmallInteger)


class ResidentialSpeedLimit(Base):
    __tablename__ = "residential_speed_limit"

    state_fips_code: Mapped[str] = mapped_column(CHAR(2))
    city_fips_code: Mapped[str] = mapped_column(CHAR(7), primary_key=True)
    state_speed: Mapped[int] = mapped_column(SmallInteger)
    city_speed: Mapped[int] = mapped_column(SmallInteger)
