"""Tests for TSE Incident Triage Cockpit and Diagnostic Endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.api.app import app
from comp_flow.core.database import get_db
from comp_flow.core.ledger import SoxLedgerService
from comp_flow.core.security import create_access_token
from comp_flow.domain.entities import (
    CompensationCycle,
    Employee,
    EmployeeReview,
    User,
)
from comp_flow.domain.models import (
    CycleStatus,
    JobLevel,
    PerformanceRating,
    ReviewStatus,
)
from comp_flow.service.tse_triage import TseIncidentTriageService


@pytest.mark.asyncio
async def test_tse_triage_compliant_review(
    seeded_test_db: dict[str, object],
    test_db_session: AsyncSession,
) -> None:
    """Verifies that a compliant review produces a HEALTHY diagnostic report."""
    db = test_db_session
    emp = seeded_test_db["emp"]
    assert isinstance(emp, Employee)

    # 1. Create a cycle
    cycle = CompensationCycle(
        id=uuid.uuid4(),
        name="FY2026 Annual Rewards",
        fiscal_year=2026,
        cycle_type="MERIT_ANNUAL",
        global_merit_budget_pct=Decimal("4.50"),
        bonus_pool_funding_pct=Decimal("100.00"),
        company_performance_factor=Decimal("1.00"),
        status=CycleStatus.ACTIVE,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db.add(cycle)
    await db.flush()

    # 2. Create an in-band proposed review ($250k base, mid is $250k)
    review = EmployeeReview(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        employee_id=emp.id,
        proposed_job_level=JobLevel.L5,
        current_base=Decimal("230000.00"),
        proposed_base=Decimal("250000.00"),
        proposed_bonus_amount=Decimal("37500.00"),
        proposed_equity_rsus=900,
        performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        status=ReviewStatus.AUTO_APPROVED,
        justification_notes="Consistent high deliverable execution",
    )
    db.add(review)
    await db.flush()

    # Record SOX ledger block
    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=review.id,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={
            "proposed_base": "250000.00",
            "decision": "AUTO_APPROVED",
        },
        trace_id="trace_test_compliant",
    )

    # Run TSE triage
    report = await TseIncidentTriageService.diagnose(
        db=db,
        review_id=review.id,
    )

    assert report.entity_type == "EMPLOYEE_REVIEW"
    assert report.entity_id == review.id
    assert report.target_name == emp.full_name
    assert report.ledger_integrity.is_valid is True
    assert report.ledger_integrity.status == "SECURE"
    assert report.root_cause_category == "HEALTHY_AUTO_APPROVED"
    assert "compliant" in report.customer_summary.lower()


@pytest.mark.asyncio
async def test_tse_triage_out_of_band_ceiling(
    seeded_test_db: dict[str, object],
    test_db_session: AsyncSession,
) -> None:
    """Verifies that an out-of-band salary is accurately diagnosed with root cause & actions."""
    db = test_db_session
    emp = seeded_test_db["emp"]
    assert isinstance(emp, Employee)

    cycle = CompensationCycle(
        id=uuid.uuid4(),
        name="FY2026 Annual Rewards",
        fiscal_year=2026,
        cycle_type="MERIT_ANNUAL",
        global_merit_budget_pct=Decimal("4.50"),
        bonus_pool_funding_pct=Decimal("100.00"),
        company_performance_factor=Decimal("1.00"),
        status=CycleStatus.ACTIVE,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db.add(cycle)
    await db.flush()

    # L5 max is $290k. Propose $350k (way above max ceiling)
    review = EmployeeReview(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        employee_id=emp.id,
        proposed_job_level=JobLevel.L5,
        current_base=Decimal("230000.00"),
        proposed_base=Decimal("350000.00"),
        proposed_bonus_amount=Decimal("52500.00"),
        proposed_equity_rsus=1500,
        performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        status=ReviewStatus.VP_EXCEPTION_REQUIRED,
        justification_notes="Executive market adjustment requested",
    )
    db.add(review)
    await db.flush()

    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=review.id,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={"proposed_base": "350000.00", "decision": "VP_EXCEPTION_REQUIRED"},
    )

    report = await TseIncidentTriageService.diagnose(
        db=db,
        review_id=review.id,
    )

    assert report.root_cause_category == "OUT_OF_BAND_COMPENSATION_CEILING"
    assert "exceeds" in report.customer_summary.lower()
    assert report.compa_ratio is not None
    assert report.compa_ratio > Decimal("1.20")
    assert len(report.recommended_actions) >= 2


@pytest.mark.asyncio
async def test_tse_trace_id_correlation(
    seeded_test_db: dict[str, object],
    test_db_session: AsyncSession,
) -> None:
    """Verifies that TSE diagnosis correlates incident directly via W3C trace ID."""
    db = test_db_session
    emp = seeded_test_db["emp"]
    assert isinstance(emp, Employee)

    unique_trace_id = "51433c5971c04337b54e1be22ce01350"

    cycle = CompensationCycle(
        id=uuid.uuid4(),
        name="FY2026 Annual Rewards",
        fiscal_year=2026,
        cycle_type="MERIT_ANNUAL",
        global_merit_budget_pct=Decimal("4.50"),
        bonus_pool_funding_pct=Decimal("100.00"),
        company_performance_factor=Decimal("1.00"),
        status=CycleStatus.ACTIVE,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db.add(cycle)
    await db.flush()

    review = EmployeeReview(
        id=uuid.uuid4(),
        cycle_id=cycle.id,
        employee_id=emp.id,
        proposed_job_level=JobLevel.L5,
        current_base=Decimal("170000.00"),
        proposed_base=Decimal("185000.00"),
        proposed_bonus_amount=Decimal("27750.00"),
        proposed_equity_rsus=1500,
        performance_rating=PerformanceRating.CONSISTENTLY_MEETS,
        status=ReviewStatus.AUTO_APPROVED,
    )
    db.add(review)
    await db.flush()

    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=review.id,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={"proposed_base": "185000.00"},
        trace_id=unique_trace_id,
    )

    # Query ONLY by trace_id
    report = await TseIncidentTriageService.diagnose(
        db=db,
        trace_id=unique_trace_id,
    )

    assert report.entity_id == review.id
    assert report.target_name == emp.full_name
    assert report.trace_id == unique_trace_id


@pytest.mark.asyncio
async def test_tse_api_diagnose_and_verify(
    seeded_test_db: dict[str, object],
    test_db_session: AsyncSession,
) -> None:
    """Verifies FastAPI HTTP endpoints for TSE diagnosis and ledger verification."""
    admin = seeded_test_db["admin"]
    assert isinstance(admin, User)

    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(admin.email, admin.role)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Verify ledger
        verify_resp = await client.get("/api/v1/tse/ledger/verify", headers=headers)
        assert verify_resp.status_code == 200
        v_data = verify_resp.json()
        assert v_data["status"] == "SECURE"

        # 2. Diagnose unresolved target
        diag_resp = await client.post(
            "/api/v1/tse/diagnose",
            headers=headers,
            json={"trace_id": "nonexistent_trace"},
        )
        assert diag_resp.status_code == 200
        d_data = diag_resp.json()
        assert d_data["root_cause_category"] == "UNRESOLVED_TARGET"

    app.dependency_overrides.clear()
