"""Integration tests for FastAPI REST Endpoints, Services, and RBAC."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.domain.entities import (
    CandidateOffer,
    CompensationCycle,
    Department,
    Employee,
)
from comp_flow.domain.models import (
    CycleStatus,
    OfferStatus,
    ReviewStatus,
    UserRole,
)


@pytest.mark.asyncio
async def test_system_healthz_and_readyz(async_client: AsyncClient) -> None:
    """Verifies liveness and readiness probe endpoints."""
    # Liveness
    res_health = await async_client.get("/healthz")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "HEALTHY"

    # Readiness
    res_ready = await async_client.get("/readyz")
    assert res_ready.status_code == 200
    assert "status" in res_ready.json()

    # Metrics
    res_metrics = await async_client.get("/metrics")
    assert res_metrics.status_code == 200
    assert "compflow_" in res_metrics.text


@pytest.mark.asyncio
async def test_auth_login_and_me(async_client: AsyncClient, seeded_test_db: dict[str, Any]) -> None:
    """Verifies user login with email/password and retrieving /me profile."""
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "Password123!"},
    )
    assert res_login.status_code == 200
    data = res_login.json()
    assert "access_token" in data
    assert data["user_role"] == UserRole.HR_ADMIN.value

    token = data["access_token"]
    res_me = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    assert res_me.json()["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_salary_bands_endpoints(
    async_client: AsyncClient, admin_token: str, manager_token: str
) -> None:
    """Verifies listing and creating salary bands with RBAC enforcement."""
    # List bands as manager
    res_list = await async_client.get(
        "/api/v1/bands", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # Upsert band as HR_ADMIN
    res_create = await async_client.post(
        "/api/v1/bands",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "job_level": "L6",
            "job_family": "SOFTWARE_ENGINEERING",
            "location_tier": "US_ZONE_1",
            "min_base": "260000.00",
            "mid_base": "310000.00",
            "max_base": "360000.00",
            "target_equity_rsus": 1400,
            "target_bonus_pct": "20.00",
        },
    )
    assert res_create.status_code == 200
    assert res_create.json()["job_level"] == "L6"


@pytest.mark.asyncio
async def test_compensation_cycle_full_lifecycle(
    async_client: AsyncClient,
    admin_token: str,
    manager_token: str,
    seeded_test_db: dict[str, Any],
) -> None:
    """Verifies creating cycle, adding proposals, auditing, approving, and finalizing cycle."""
    emp = seeded_test_db["emp"]
    dept = seeded_test_db["dept"]
    assert isinstance(emp, Employee)
    assert isinstance(dept, Department)

    # 1. Create Cycle as Admin
    cycle_res = await async_client.post(
        "/api/v1/cycles",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "2026 Annual Planning",
            "fiscal_year": "FY2026",
            "cycle_type": "ANNUAL_TOTAL_REWARDS",
            "global_merit_budget_pct": "4.50",
            "bonus_pool_funding_pct": "100.00",
            "company_performance_factor": "1.00",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=60)),
        },
    )
    assert cycle_res.status_code == 200
    cycle_id = cycle_res.json()["id"]

    # 2. Check Department Budget Rollup
    budget_res = await async_client.get(
        f"/api/v1/cycles/{cycle_id}/budgets/{dept.id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert budget_res.status_code == 200
    assert budget_res.json()["department_name"] == "Platform Engineering"
    assert Decimal(budget_res.json()["allocated_merit_budget"]) > Decimal("0.00")

    # 3. Manager Submits Proposal (Compliant)
    proposal_res = await async_client.post(
        f"/api/v1/cycles/{cycle_id}/proposals",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={
            "cycle_id": cycle_id,
            "employee_id": str(emp.id),
            "proposed_job_level": "L5",
            "proposed_base": "245000.00",  # +6.5% raise
            "proposed_bonus_amount": "36750.00",  # 15% target
            "individual_perf_factor": "1.00",
            "proposed_equity_rsus": 900,
            "performance_rating": "CONSISTENTLY_MEETS",
            "justification_notes": "Great contributions to platform reliability.",
        },
    )
    assert proposal_res.status_code == 200
    proposal_data = proposal_res.json()
    proposal_id = proposal_data["id"]
    assert proposal_data["status"] == ReviewStatus.DRAFT.value

    # 4. Trigger Agentic Audit on Proposal
    audit_res = await async_client.post(
        f"/api/v1/proposals/{proposal_id}/audit",
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert audit_res.status_code == 200
    assert audit_res.json()["decision"] == ReviewStatus.AUTO_APPROVED.value

    # 5. Finalize Cycle as Admin
    final_res = await async_client.post(
        f"/api/v1/cycles/{cycle_id}/finalize",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert final_res.status_code == 200
    assert final_res.json()["status"] == CycleStatus.FINALIZED.value

    # 6. Check Analytics
    analytics_res = await async_client.get(
        f"/api/v1/analytics/cycles/{cycle_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert analytics_res.status_code == 200
    assert analytics_res.json()["total_proposals"] == 1


@pytest.mark.asyncio
async def test_candidate_offer_full_lifecycle(
    async_client: AsyncClient,
    admin_token: str,
    recruiter_token: str,
    seeded_test_db: dict[str, Any],
) -> None:
    """Verifies Candidate Offer creation, audit, VP exception approval, extending, and acceptance."""
    dept = seeded_test_db["dept"]
    assert isinstance(dept, Department)

    # 1. Recruiter Creates Offer (with high sign-on bonus $60k -> requires VP exception)
    offer_res = await async_client.post(
        "/api/v1/offers",
        headers={"Authorization": f"Bearer {recruiter_token}"},
        json={
            "candidate_name": "Devin AI",
            "candidate_email": "devin@candidate.test",
            "job_level": "L5",
            "job_family": "SOFTWARE_ENGINEERING",
            "location_tier": "US_ZONE_1",
            "department_id": str(dept.id),
            "proposed_base": "240000.00",
            "sign_on_bonus": "60000.00",  # > $50,000 threshold
            "proposed_equity_rsus": 1000,
            "target_start_date": str(date.today() + timedelta(days=30)),
            "notes": "Top tier candidate with specialized kernel expertise.",
        },
    )
    assert offer_res.status_code == 200
    offer_data = offer_res.json()
    offer_id = offer_data["id"]
    assert offer_data["status"] == OfferStatus.OFFER_DRAFT.value

    # 2. Run Audit
    audit_res = await async_client.post(
        f"/api/v1/offers/{offer_id}/audit",
        headers={"Authorization": f"Bearer {recruiter_token}"},
    )
    assert audit_res.status_code == 200
    assert audit_res.json()["decision"] == OfferStatus.VP_EXCEPTION_REQUIRED.value

    # 3. VP / Admin Approves Exception
    approve_res = await async_client.post(
        f"/api/v1/offers/{offer_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"notes": "Approved sign-on bonus for critical skills match."},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == OfferStatus.OFFER_APPROVED.value

    # 4. Recruiter Extends Offer
    extend_res = await async_client.post(
        f"/api/v1/offers/{offer_id}/extend",
        headers={"Authorization": f"Bearer {recruiter_token}"},
        json={"notes": "Offer letter sent to candidate via DocuSign."},
    )
    assert extend_res.status_code == 200
    assert extend_res.json()["status"] == OfferStatus.OFFER_EXTENDED.value

    # 5. Record Candidate Acceptance
    decision_res = await async_client.post(
        f"/api/v1/offers/{offer_id}/decision?target_status=OFFER_ACCEPTED",
        headers={"Authorization": f"Bearer {recruiter_token}"},
        json={"notes": "Candidate signed and verified start date."},
    )
    assert decision_res.status_code == 200
    assert decision_res.json()["status"] == OfferStatus.OFFER_ACCEPTED.value

    # 6. List and filter offers
    res_list = await async_client.get(
        "/api/v1/offers?status=OFFER_ACCEPTED",
        headers={"Authorization": f"Bearer {recruiter_token}"},
    )
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1


@pytest.mark.asyncio
async def test_batch_audit_and_rbac_forbidden(
    async_client: AsyncClient,
    admin_token: str,
    manager_token: str,
    recruiter_token: str,
    seeded_test_db: dict[str, Any],
) -> None:
    """Verifies batch audit endpoint and RBAC forbidden status codes."""
    emp = seeded_test_db["emp"]
    assert isinstance(emp, Employee)

    # 1. Create cycle
    cycle_res = await async_client.post(
        "/api/v1/cycles",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Batch Audit Cycle",
            "fiscal_year": "FY2026",
            "cycle_type": "ANNUAL_TOTAL_REWARDS",
            "global_merit_budget_pct": "5.00",
            "bonus_pool_funding_pct": "100.00",
            "company_performance_factor": "1.00",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=60)),
        },
    )
    cycle_id = cycle_res.json()["id"]

    # 2. Add proposal
    p_res = await async_client.post(
        f"/api/v1/cycles/{cycle_id}/proposals",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={
            "cycle_id": cycle_id,
            "employee_id": str(emp.id),
            "proposed_job_level": "L5",
            "proposed_base": "240000.00",
            "proposed_bonus_amount": "36000.00",
            "individual_perf_factor": "1.00",
            "proposed_equity_rsus": 900,
            "performance_rating": "CONSISTENTLY_MEETS",
            "justification_notes": "Test batch",
        },
    )
    p_id = p_res.json()["id"]

    # 3. Batch Audit
    batch_res = await async_client.post(
        f"/api/v1/cycles/{cycle_id}/batch-audit",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"proposal_ids": [p_id]},
    )
    assert batch_res.status_code == 200
    assert batch_res.json()["total_audited"] == 1

    # 4. RBAC: Recruiter forbidden from finalizing cycle
    forbid_res = await async_client.post(
        f"/api/v1/cycles/{cycle_id}/finalize",
        headers={"Authorization": f"Bearer {recruiter_token}"},
    )
    assert forbid_res.status_code == 403


@pytest.mark.asyncio
async def test_enterprise_seeder_integration(test_db_session: AsyncSession) -> None:
    """Verifies that the enterprise seed script executes cleanly and populates tables."""
    from comp_flow.cli.seeder import seed_enterprise_data

    await seed_enterprise_data(test_db_session)

    # Verify counts in test DB
    emp_res = await test_db_session.execute(select(Employee))
    employees = emp_res.scalars().all()
    assert len(employees) >= 50

    dept_res = await test_db_session.execute(select(Department))
    departments = dept_res.scalars().all()
    assert len(departments) == 3

    cycle_res = await test_db_session.execute(select(CompensationCycle))
    cycles = cycle_res.scalars().all()
    assert len(cycles) >= 1

    offers_res = await test_db_session.execute(select(CandidateOffer))
    offers = offers_res.scalars().all()
    assert len(offers) >= 3
