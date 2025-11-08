from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, TIMESTAMP, Date
from sqlalchemy.sql import func
from database.connection import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(100))
    language = Column(String(10), default="en")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    company_number = Column(String(50), unique=True, index=True)
    registered_address = Column(Text)
    status = Column(String(50), default="unknown")
    score = Column(Integer, default=0)
    website_domain = Column(String(255))
    contact_email = Column(String(255))
    phone_number = Column(String(50))
    last_updated = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class UserCheck(Base):
    __tablename__ = "user_checks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"))
    contract_number = Column(String(100))
    contract_date = Column(Date)
    extracted_company_name = Column(String(255))
    extracted_company_number = Column(String(50))
    extracted_address = Column(Text)
    website_domain = Column(String(255))
    total_score = Column(Integer, default=0)
    safety_rating = Column(String(10), default="unknown")
    detailed_scores = Column(JSON)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())


class SuspiciousCompany(Base):
    __tablename__ = "suspicious_companies"

    id = Column(Integer, primary_key=True)
    company_name = Column(String(255), nullable=False)
    company_number = Column(String(50), unique=True)
    evidence = Column(Text)
    source = Column(String(100))
    status = Column(String(20), default="active")
    website_domain = Column(String(255))
    registered_address = Column(Text)
    contact_phone = Column(String(50))
    contact_email = Column(String(255))
    added_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    verified_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
