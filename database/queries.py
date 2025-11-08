from database.models import User, Company, UserCheck, SuspiciousCompany
from database.connection import AsyncSessionLocal
from typing import Optional, List, Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, func, case, delete
from datetime import datetime
import zipfile
import csv
import os



ADMIN_STATE_ADD: Dict[int, str] = {}



async def add_user(telegram_id: str, username: Optional[str] = None, language: str = 'ru') -> bool:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if result:
                return True 

            new_user = User(telegram_id=telegram_id, username=username, language=language)
            session.add(new_user)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"❌ Error adding user: {e}")
            return False


async def get_lang(telegram_id: str) -> Optional[str]:
    async with AsyncSessionLocal() as session:
        try:
            user = await session.scalar(select(User).where(User.telegram_id == str(telegram_id)))
            return user.language if user else None
        except SQLAlchemyError as e:
            print(f"❌ Error fetching language: {e}")
            return None


async def change_language(telegram_id: str, new_language: str) -> bool:
    async with AsyncSessionLocal() as session:
        try:
            user = await session.scalar(select(User).where(User.telegram_id == str(telegram_id)))
            if not user:
                return False
            user.language = new_language
            await session.commit()
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"❌ Error changing language: {e}")
            return False


async def add_company(data: Dict[str, Any]) -> Optional[int]:
    data = {
        **data,
        'last_updated': datetime.utcnow()
    }

    async with AsyncSessionLocal() as session:
        try:
            existing = await session.scalar(
                select(Company).where(Company.company_number == data["company_number"])
            )

            if existing:
                for key, value in data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                filtered_data = {k: v for k, v in data.items() if hasattr(Company, k)}
                company = Company(**filtered_data)
                session.add(company)
                existing = company

            await session.commit()
            await session.refresh(existing)
            return existing.id

        except SQLAlchemyError as e:
            await session.rollback()
            print(f"Error adding/updating company: {e}")
            return None


async def get_company_by_number(company_number: str) -> Optional[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Company).where(Company.company_number == company_number)
            )
            company = result.scalar_one_or_none()
            if company:
                return {
                    "id": company.id,
                    "name": company.name,
                    "company_number": company.company_number,
                    "registered_address": company.registered_address,
                    "status": company.status,
                    "score": company.score,
                    "website_domain": company.website_domain,
                    "contact_email": company.contact_email,
                    "phone_number": company.phone_number,
                    "last_updated": company.last_updated, 
                    "created_at": company.created_at
                }
            return None
        except Exception as e:
            print(f"Error fetching company: {e}")
            return None


async def add_user_check(check_data: Dict[str, Any]) -> Optional[int]:
    async with AsyncSessionLocal() as session:
        try:
            new_check = UserCheck(
                user_id=check_data.get('user_id'),
                company_id=check_data.get('company_id'),
                contract_number=check_data.get('contract_number'),
                contract_date=check_data.get('contract_date'),
                extracted_company_name=check_data.get('extracted_company_name'),
                extracted_company_number=check_data.get('extracted_company_number'),
                extracted_address=check_data.get('extracted_address'),
                website_domain=check_data.get('website_domain'),
                total_score=check_data.get('total_score', 0),
                safety_rating=check_data.get('safety_rating', 'unknown'),
                detailed_scores=check_data.get('detailed_scores', {}),
            )
            session.add(new_check)
            await session.commit()
            await session.refresh(new_check)
            print(f"✅ User check added successfully (ID={new_check.id})")
            return new_check.id
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"❌ Error adding user check: {e}")
            return None


async def get_user_checks_history(user_id: int, limit: int = 10) -> List[Dict]:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(UserCheck, Company.name.label("company_name"))
                .join(Company, Company.id == UserCheck.company_id, isouter=True)
                .where(UserCheck.user_id == user_id)
                .order_by(UserCheck.created_at.desc())
                .limit(limit)
            )
            rows = []
            for check, company_name in result.all():
                data = check.__dict__.copy()
                data["company_name"] = company_name
                rows.append(data)
            return rows
        except SQLAlchemyError as e:
            print(f"❌ Error fetching checks history: {e}")
            return []


async def add_suspicious_company(data: Dict[str, Any]) -> Optional[int]:
    async with AsyncSessionLocal() as session:
        try:
            existing = await session.scalar(
                select(SuspiciousCompany).where(SuspiciousCompany.company_number == data.get("company_number"))
            )
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                existing = SuspiciousCompany(**data)
                session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing.id
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"❌ Error adding suspicious company: {e}")
            return None


async def check_suspicious_company(company_number: str = None, company_name: str = None) -> Optional[Dict]:
    async with AsyncSessionLocal() as session:
        try:
            if company_number:
                stmt = select(SuspiciousCompany).where(
                    SuspiciousCompany.company_number == company_number,
                    SuspiciousCompany.status == "active"
                )
            elif company_name:
                stmt = select(SuspiciousCompany).where(
                    SuspiciousCompany.company_name.ilike(f"%{company_name}%"),
                    SuspiciousCompany.status == "active"
                )
            else:
                return None

            company = await session.scalar(stmt)
            return company.__dict__ if company else None
        except SQLAlchemyError as e:
            print(f"❌ Error checking suspicious company: {e}")
            return None


async def get_user_by_telegram_id(telegram_id: str) -> Optional[Dict]:
    async with AsyncSessionLocal() as session:
        try:
            user = await session.scalar(select(User).where(User.telegram_id == str(telegram_id)))
            return user.__dict__ if user else None
        except SQLAlchemyError as e:
            print(f"❌ Error fetching user: {e}")
            return None


async def get_check_by_id(check_id: int) -> Optional[Dict]:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(UserCheck, Company.name.label("company_name"))
                .join(Company, Company.id == UserCheck.company_id, isouter=True)
                .where(UserCheck.id == check_id)
            )
            row = result.first()
            if not row:
                return None
            check, company_name = row
            data = check.__dict__.copy()
            data["company_name"] = company_name
            return data
        except SQLAlchemyError as e:
            print(f"❌ Error fetching check: {e}")
            return None


async def get_companies_by_name(company_name: str) -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(Company).where(func.lower(Company.name) == company_name.lower())
            result = await session.execute(stmt)
            companies = result.scalars().all()
            return [company.__dict__ for company in companies]
        except SQLAlchemyError as e:
            print(f"❌ Error fetching companies by name: {e}")
            return []
        


async def delete_company_by_number(company_number: str) -> bool:
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                delete(Company).where(Company.company_number == company_number)
            )
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            await session.rollback()
            print(f"Error deleting company: {e}")
            return False


