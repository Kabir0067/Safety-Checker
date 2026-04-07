from database.models import User, Company, UserCheck, SuspiciousCompany, SuspiciousEntity
from database.connection import AsyncSessionLocal
from typing import Optional, List, Dict, Any
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, func, case, delete, and_, or_
from datetime import UTC, datetime, date
import zipfile
import csv
import os



ADMIN_STATE_ADD: Dict[int, str] = {}


def _clean_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _clean_optional_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True



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
    cleaned_data = {
        **data,
        "name": _clean_optional_string(data.get("name")),
        "company_number": _clean_optional_string(data.get("company_number")),
        "registered_address": _clean_optional_string(data.get("registered_address")),
        "website_domain": _clean_optional_string(data.get("website_domain")),
        "contact_email": _clean_optional_string(data.get("contact_email")),
        "phone_number": _clean_optional_string(data.get("phone_number")),
        "incorporation_date": _clean_optional_date(data.get("incorporation_date")),
        "last_updated": datetime.now(UTC),
    }

    async with AsyncSessionLocal() as session:
        try:
            existing = None
            company_number = cleaned_data.get("company_number")

            if company_number:
                existing = await session.scalar(
                    select(Company).where(Company.company_number == company_number)
                )
            else:
                name = cleaned_data.get("name")
                registered_address = cleaned_data.get("registered_address")
                website_domain = cleaned_data.get("website_domain")

                if name and registered_address:
                    existing = await session.scalar(
                        select(Company).where(
                            and_(
                                func.lower(Company.name) == name.lower(),
                                func.lower(Company.registered_address) == registered_address.lower(),
                                Company.company_number.is_(None),
                            )
                        )
                    )
                elif name and website_domain:
                    existing = await session.scalar(
                        select(Company).where(
                            and_(
                                func.lower(Company.name) == name.lower(),
                                func.lower(Company.website_domain) == website_domain.lower(),
                                Company.company_number.is_(None),
                            )
                        )
                    )

            if existing:
                for key, value in cleaned_data.items():
                    if not hasattr(existing, key):
                        continue
                    if key == "last_updated" or _is_meaningful(value):
                        setattr(existing, key, value)
            else:
                if not cleaned_data.get("name"):
                    return None
                filtered_data = {k: v for k, v in cleaned_data.items() if hasattr(Company, k)}
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
                    "incorporation_date": company.incorporation_date,
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
                contract_template_hash=check_data.get('contract_template_hash'),
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
            company_number = _clean_optional_string(data.get("company_number"))
            company_name = _clean_optional_string(data.get("company_name"))
            website_domain = _clean_optional_string(data.get("website_domain"))
            registered_address = _clean_optional_string(data.get("registered_address"))

            normalized_data = {
                **data,
                "company_number": company_number,
                "company_name": company_name or (company_number and f"Company {company_number}"),
                "website_domain": website_domain,
                "registered_address": registered_address,
                "contact_phone": _clean_optional_string(data.get("contact_phone")),
                "contact_email": _clean_optional_string(data.get("contact_email")),
            }

            existing = None
            if company_number:
                existing = await session.scalar(
                    select(SuspiciousCompany).where(SuspiciousCompany.company_number == company_number)
                )
            elif company_name and registered_address:
                existing = await session.scalar(
                    select(SuspiciousCompany).where(
                        and_(
                            func.lower(SuspiciousCompany.company_name) == company_name.lower(),
                            func.lower(SuspiciousCompany.registered_address) == registered_address.lower(),
                            SuspiciousCompany.company_number.is_(None),
                        )
                    )
                )
            elif company_name and website_domain:
                existing = await session.scalar(
                    select(SuspiciousCompany).where(
                        and_(
                            func.lower(SuspiciousCompany.company_name) == company_name.lower(),
                            func.lower(SuspiciousCompany.website_domain) == website_domain.lower(),
                            SuspiciousCompany.company_number.is_(None),
                        )
                    )
                )
            elif company_name:
                existing = await session.scalar(
                    select(SuspiciousCompany).where(
                        and_(
                            func.lower(SuspiciousCompany.company_name) == company_name.lower(),
                            SuspiciousCompany.company_number.is_(None),
                        )
                    )
                )

            if existing:
                for key, value in normalized_data.items():
                    if hasattr(existing, key) and _is_meaningful(value):
                        setattr(existing, key, value)
            else:
                if not normalized_data.get("company_name"):
                    return None
                existing = SuspiciousCompany(**normalized_data)
                session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing.id
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"❌ Error adding suspicious company: {e}")
            return None


async def add_suspicious_entity(data: Dict[str, Any]) -> Optional[int]:
    async with AsyncSessionLocal() as session:
        try:
            normalized_data = {
                "email_domain": _clean_optional_string(data.get("email_domain")),
                "phone_number": _clean_optional_string(data.get("phone_number")),
                "recruiter_name": _clean_optional_string(data.get("recruiter_name")),
                "contract_template_hash": _clean_optional_string(data.get("contract_template_hash")),
                "source": _clean_optional_string(data.get("source")),
            }

            dedupe_filters = [
                getattr(SuspiciousEntity, key) == value
                for key, value in normalized_data.items()
                if value is not None and key != "source"
            ]
            existing = None
            if dedupe_filters:
                existing = await session.scalar(
                    select(SuspiciousEntity).where(and_(*dedupe_filters))
                )
            if existing:
                return existing.id

            entity = SuspiciousEntity(**normalized_data)
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity.id
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"Error adding suspicious entity: {e}")
            return None


async def find_suspicious_entity_matches(
    email_domain: str = None,
    phone_number: str = None,
    recruiter_name: str = None,
    contract_template_hash: str = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        try:
            filters = []
            if email_domain:
                filters.append(func.lower(SuspiciousEntity.email_domain) == email_domain.lower())
            if phone_number:
                filters.append(SuspiciousEntity.phone_number == phone_number)
            if recruiter_name:
                filters.append(func.lower(SuspiciousEntity.recruiter_name) == recruiter_name.lower())
            if contract_template_hash:
                filters.append(SuspiciousEntity.contract_template_hash == contract_template_hash)

            if not filters:
                return []

            stmt = (
                select(SuspiciousEntity)
                .where(or_(*filters))
                .order_by(SuspiciousEntity.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            matches = []
            for entity in result.scalars().all():
                matches.append(
                    {
                        "id": entity.id,
                        "email_domain": entity.email_domain,
                        "phone_number": entity.phone_number,
                        "recruiter_name": entity.recruiter_name,
                        "contract_template_hash": entity.contract_template_hash,
                        "source": entity.source,
                        "created_at": entity.created_at,
                    }
                )
            return matches
        except SQLAlchemyError as e:
            print(f"Error finding suspicious entity matches: {e}")
            return []


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


async def get_distinct_company_names_by_template(template_hash: str) -> List[str]:
    if not template_hash:
        return []
    async with AsyncSessionLocal() as session:
        try:
            stmt = select(UserCheck.extracted_company_name).where(
                UserCheck.contract_template_hash == template_hash
            )
            result = await session.execute(stmt)
            names = []
            for row in result.fetchall():
                name = row[0]
                if name and isinstance(name, str) and name.strip():
                    names.append(name.strip())
            return list(dict.fromkeys(names))
        except SQLAlchemyError as e:
            print(f"Error fetching template company names: {e}")
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


