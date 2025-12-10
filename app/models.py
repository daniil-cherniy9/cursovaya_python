from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_hr = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи
    candidates = relationship("Candidate", back_populates="recruiter")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    phone = Column(String(20))
    position = Column(String(100))
    status = Column(String(20), default="new")  # new, interview, hired, rejected
    experience_years = Column(Integer, default=0)
    resume_url = Column(String(255))
    notes = Column(Text)
    recruiter_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Связи
    recruiter = relationship("User", back_populates="candidates")
    applications = relationship("VacancyApplication", back_populates="candidate")


class Vacancy(Base):
    __tablename__ = "vacancies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    department = Column(String(50))
    description = Column(Text)
    requirements = Column(Text)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    status = Column(String(20), default="open")
    location = Column(String(100))
    employment_type = Column(String(30))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    applications = relationship("VacancyApplication", back_populates="vacancy")


class VacancyApplication(Base):
    __tablename__ = "vacancy_applications"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    vacancy_id = Column(Integer, ForeignKey("vacancies.id"), nullable=False)
    application_status = Column(String(20), default="applied")
    cover_letter = Column(Text)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)

    candidate = relationship("Candidate", back_populates="applications")
    vacancy = relationship("Vacancy", back_populates="applications")
