"""Pytest fixtures and test database setup for CompFlow."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from comp_flow.api.app import app
from comp_flow.core.database import get_db
from comp_flow.core.security import create_access_token, hash_password
from comp_flow.domain.entities import Base, Department, Employee, SalaryBand, User
from comp_flow.domain.models import (
    JobFamily,
    JobLevel,
    LocationTier,
    PerformanceRating,
    UserRole,
)
from comp_flow.tools.registry import get_default_salary_band

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated in-memory SQLite database session for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_test_db(test_db_session: AsyncSession) -> dict[str, object]:
    """Populates basic test fixtures (admin user, manager, department, salary bands, employee)."""
    db = test_db_session

    # Admin User
    admin = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        full_name="Admin Test",
        hashed_password=hash_password("Password123!"),
        role=UserRole.HR_ADMIN,
        is_active=True,
    )
    db.add(admin)

    # Manager User
    manager = User(
        id=uuid.uuid4(),
        email="manager@test.com",
        full_name="Manager Test",
        hashed_password=hash_password("Password123!"),
        role=UserRole.PEOPLE_MANAGER,
        is_active=True,
    )
    db.add(manager)

    # Recruiter User
    recruiter = User(
        id=uuid.uuid4(),
        email="recruiter@test.com",
        full_name="Recruiter Test",
        hashed_password=hash_password("Password123!"),
        role=UserRole.RECRUITER,
        is_active=True,
    )
    db.add(recruiter)

    # Department
    dept = Department(
        id=uuid.uuid4(),
        name="Platform Engineering",
        cost_center="CC-5000",
        head_of_department_id=manager.id,
    )
    db.add(dept)

    # Salary Band (L5 SWE Zone 1)
    b_l5 = get_default_salary_band(
        JobLevel.L5, JobFamily.SOFTWARE_ENGINEERING, LocationTier.US_ZONE_1
    )
    band = SalaryBand(
        id=uuid.uuid4(),
        job_level=b_l5.job_level,
        job_family=b_l5.job_family,
        location_tier=b_l5.location_tier,
        min_base=b_l5.min_base,
        mid_base=b_l5.mid_base,
        max_base=b_l5.max_base,
        target_equity_gsus=b_l5.target_equity_gsus,
        target_bonus_pct=b_l5.target_bonus_pct,
    )
    db.add(band)

    # Employee
    emp = Employee(
        id=uuid.uuid4(),
        employee_number="EMP-TEST-001",
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@test.com",
        job_level=JobLevel.L5,
        job_family=JobFamily.SOFTWARE_ENGINEERING,
        location_tier=LocationTier.US_ZONE_1,
        department_id=dept.id,
        current_base=Decimal("230000.00"),
        current_equity_gsus=2700,
        last_performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        is_active=True,
    )
    db.add(emp)

    await db.commit()

    return {
        "admin": admin,
        "manager": manager,
        "recruiter": recruiter,
        "dept": dept,
        "band": band,
        "emp": emp,
        "db": db,
    }


@pytest_asyncio.fixture
async def async_client(test_db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provides an AsyncClient connected to FastAPI app with overridden DB session."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(seeded_test_db: dict[str, object]) -> str:
    """Generates valid JWT for test admin."""
    admin = seeded_test_db["admin"]
    assert isinstance(admin, User)
    return create_access_token(admin.email, admin.role)


@pytest.fixture
def manager_token(seeded_test_db: dict[str, object]) -> str:
    """Generates valid JWT for test manager."""
    manager = seeded_test_db["manager"]
    assert isinstance(manager, User)
    return create_access_token(manager.email, manager.role)


@pytest.fixture
def recruiter_token(seeded_test_db: dict[str, object]) -> str:
    """Generates valid JWT for test recruiter."""
    recruiter = seeded_test_db["recruiter"]
    assert isinstance(recruiter, User)
    return create_access_token(recruiter.email, recruiter.role)
