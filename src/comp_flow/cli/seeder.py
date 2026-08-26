"""Enterprise Demonstration Data Seeder for CompFlow Platform."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import AsyncSessionLocal, init_db
from comp_flow.core.security import hash_password
from comp_flow.domain.entities import (
    CandidateOffer,
    CompensationCycle,
    CycleBudget,
    Department,
    Employee,
    EmployeeReview,
    SalaryBand,
    User,
)
from comp_flow.domain.models import (
    CycleStatus,
    JobFamily,
    JobLevel,
    LocationTier,
    OfferStatus,
    PerformanceRating,
    ReviewStatus,
    SalaryBandBase,
    UserRole,
)
from comp_flow.service.cycle_service import CycleService
from comp_flow.service.offer_service import OfferService
from comp_flow.tools.registry import (
    calculate_compa_ratio,
    calculate_offer_total_comp,
    get_default_salary_band,
)

logger = logging.getLogger(__name__)


async def seed_enterprise_data(session: AsyncSession | None = None) -> None:
    """Populates PostgreSQL with realistic enterprise datasets for live demonstration."""
    owns_session = session is None
    db = session or AsyncSessionLocal()

    try:
        # Initialize schema tables if running standalone
        if owns_session:
            await init_db()

        # 1. Seed Demo Users
        users_data: list[tuple[str, str, UserRole]] = [
            ("admin@compflow.internal", "Elena Rostova (HR VP)", UserRole.HR_ADMIN),
            (
                "partner@compflow.internal",
                "Marcus Vance (Comp Director)",
                UserRole.COMPENSATION_PARTNER,
            ),
            (
                "manager.infra@compflow.internal",
                "Sarah Chen (Infra Director)",
                UserRole.PEOPLE_MANAGER,
            ),
            (
                "exec@compflow.internal",
                "David Sterling (VP Engineering)",
                UserRole.EXECUTIVE_APPROVER,
            ),
            (
                "recruiter@compflow.internal",
                "Jordan Taylor (Lead Tech Recruiter)",
                UserRole.RECRUITER,
            ),
        ]

        created_users: dict[str, User] = {}
        for email, full_name, role in users_data:
            user_stmt = select(User).where(User.email == email)
            existing_user = (await db.execute(user_stmt)).scalar_one_or_none()
            if not existing_user:
                u = User(
                    id=uuid.uuid4(),
                    email=email,
                    full_name=full_name,
                    hashed_password=hash_password("Password123!"),
                    role=role,
                    is_active=True,
                )
                db.add(u)
                created_users[email] = u
            else:
                created_users[email] = existing_user

        await db.flush()

        # 2. Seed Departments
        dept_data = [
            ("Core Systems & Infrastructure", "CC-1010-INFRA"),
            ("Machine Learning & AI Platform", "CC-2020-ML"),
            ("Total Rewards & People Tech", "CC-3030-HRTECH"),
        ]

        created_depts: dict[str, Department] = {}
        for name, cost_center in dept_data:
            dept_stmt = select(Department).where(Department.cost_center == cost_center)
            existing_dept = (await db.execute(dept_stmt)).scalar_one_or_none()
            if not existing_dept:
                dept = Department(
                    id=uuid.uuid4(),
                    name=name,
                    cost_center=cost_center,
                    head_of_department_id=created_users["manager.infra@compflow.internal"].id,
                )
                db.add(dept)
                created_depts[cost_center] = dept
            else:
                created_depts[cost_center] = existing_dept

        await db.flush()

        # 3. Seed Salary Bands for all Levels and Geos
        for level in JobLevel:
            for geo in LocationTier:
                for family in [JobFamily.SOFTWARE_ENGINEERING, JobFamily.SYSTEMS_INFRASTRUCTURE]:
                    band_stmt = select(SalaryBand).where(
                        SalaryBand.job_level == level,
                        SalaryBand.job_family == family,
                        SalaryBand.location_tier == geo,
                    )
                    existing_band = (await db.execute(band_stmt)).scalar_one_or_none()
                    if not existing_band:
                        b_schema = get_default_salary_band(level, family, geo)
                        band = SalaryBand(
                            id=uuid.uuid4(),
                            job_level=level,
                            job_family=family,
                            location_tier=geo,
                            min_base=b_schema.min_base,
                            mid_base=b_schema.mid_base,
                            max_base=b_schema.max_base,
                            target_equity_gsus=b_schema.target_equity_gsus,
                            target_bonus_pct=b_schema.target_bonus_pct,
                        )
                        db.add(band)

        await db.flush()

        # 4. Seed Employees across Departments (~60 employees)
        first_names = [
            "Alex",
            "Blake",
            "Casey",
            "Dana",
            "Evan",
            "Fiona",
            "Gabriel",
            "Hannah",
            "Ian",
            "Julia",
            "Kai",
            "Leo",
            "Maya",
            "Noah",
            "Olivia",
            "Priya",
            "Quinn",
            "Riley",
            "Sam",
            "Tara",
        ]
        last_names = [
            "Zhang",
            "Smith",
            "Patel",
            "Mendoza",
            "Kowalski",
            "Kim",
            "Dubois",
            "Larsson",
            "Nakamura",
            "Al-Mansoor",
            "Novak",
            "O'Connor",
            "Santos",
            "Tanaka",
            "Vogel",
        ]

        dept_list = list(created_depts.values())
        levels_pool = [
            JobLevel.L3,
            JobLevel.L4,
            JobLevel.L4,
            JobLevel.L5,
            JobLevel.L5,
            JobLevel.L5,
            JobLevel.L6,
            JobLevel.L6,
            JobLevel.L7,
            JobLevel.L8,
        ]
        ratings_pool = [
            PerformanceRating.CONSISTENTLY_MEETS,
            PerformanceRating.CONSISTENTLY_MEETS,
            PerformanceRating.EXCEEDS,
            PerformanceRating.STRONGLY_OUTPERFORMS,
            PerformanceRating.SUPERB,
        ]

        created_employees: list[Employee] = []
        for i in range(60):
            emp_num = f"EMP-{1000 + i}"
            emp_stmt = select(Employee).where(Employee.employee_number == emp_num)
            existing_emp = (await db.execute(emp_stmt)).scalar_one_or_none()
            if not existing_emp:
                fn = first_names[i % len(first_names)]
                ln = last_names[i % len(last_names)]
                lvl = levels_pool[i % len(levels_pool)]
                dept = dept_list[i % len(dept_list)]
                geo = (
                    LocationTier.US_ZONE_1
                    if i % 3 == 0
                    else (LocationTier.US_ZONE_2 if i % 3 == 1 else LocationTier.US_ZONE_3)
                )
                rating = ratings_pool[i % len(ratings_pool)]

                b_emp = get_default_salary_band(lvl, JobFamily.SOFTWARE_ENGINEERING, geo)
                # Position salary realistically near midpoint
                base_sal = b_emp.mid_base * Decimal(str(0.92 + (i % 15) * 0.01))
                base_sal = base_sal.quantize(Decimal("100.00"))

                emp = Employee(
                    id=uuid.uuid4(),
                    employee_number=emp_num,
                    first_name=fn,
                    last_name=ln,
                    email=f"{fn.lower()}.{ln.lower()}{i}@compflow.internal",
                    job_level=lvl,
                    job_family=JobFamily.SOFTWARE_ENGINEERING,
                    location_tier=geo,
                    department_id=dept.id,
                    current_base=base_sal,
                    current_equity_gsus=b_emp.target_equity_gsus * 3,
                    last_performance_rating=rating,
                    is_active=True,
                )
                db.add(emp)
                created_employees.append(emp)
            else:
                created_employees.append(existing_emp)

        await db.flush()

        # 5. Seed 2026 Compensation Cycle
        cycle_stmt = select(CompensationCycle).where(CompensationCycle.fiscal_year == "FY2026")
        cycle = (await db.execute(cycle_stmt)).scalar_one_or_none()
        if not cycle:
            cycle = CompensationCycle(
                id=uuid.uuid4(),
                name="2026 Global Total Rewards & Merit Review",
                fiscal_year="FY2026",
                cycle_type="ANNUAL_TOTAL_REWARDS",
                global_merit_budget_pct=Decimal("4.50"),
                bonus_pool_funding_pct=Decimal("105.00"),
                company_performance_factor=Decimal("1.10"),
                status=CycleStatus.ACTIVE,
                start_date=date(2026, 1, 15),
                end_date=date(2026, 3, 31),
            )
            db.add(cycle)
            await db.flush()

            # Provision department budgets
            for dept in dept_list:
                dept_emps = [e for e in created_employees if e.department_id == dept.id]
                tot_base = sum((e.current_base for e in dept_emps), Decimal("0.00"))
                budget = CycleBudget(
                    id=uuid.uuid4(),
                    cycle_id=cycle.id,
                    department_id=dept.id,
                    allocated_merit_budget=(tot_base * Decimal("0.045")).quantize(Decimal("0.01")),
                    depleted_merit_budget=Decimal("0.00"),
                    allocated_bonus_pool=(tot_base * Decimal("0.15") * Decimal("1.05")).quantize(
                        Decimal("0.01")
                    ),
                    depleted_bonus_pool=Decimal("0.00"),
                    allocated_equity_pool=len(dept_emps) * 1200,
                    depleted_equity_pool=0,
                )
                db.add(budget)

            await db.flush()

        # 6. Seed Sample Review Proposals & Run Agent Audits on subset
        manager_user = created_users["manager.infra@compflow.internal"]
        for idx, emp in enumerate(created_employees[:15]):
            rev_stmt = select(EmployeeReview).where(
                EmployeeReview.cycle_id == cycle.id, EmployeeReview.employee_id == emp.id
            )
            if not (await db.execute(rev_stmt)).scalar_one_or_none():
                # 4% - 10% raise
                raise_pct = Decimal(str(4.0 + (idx % 5) * 1.5))
                proposed_base = (
                    emp.current_base * (Decimal("1.0") + raise_pct / Decimal("100.0"))
                ).quantize(Decimal("100.00"))
                b_rev: SalaryBandBase = get_default_salary_band(
                    emp.job_level, emp.job_family, emp.location_tier
                )
                bonus_amt = (
                    proposed_base * b_rev.target_bonus_pct / Decimal("100.0") * Decimal("1.10")
                ).quantize(Decimal("0.01"))

                # Make 1 proposal trigger a VP exception intentionally (huge equity)
                equity_grant = (
                    b_rev.target_equity_gsus if idx != 2 else int(b_rev.target_equity_gsus * 2.8)
                )

                rev = EmployeeReview(
                    id=uuid.uuid4(),
                    cycle_id=cycle.id,
                    employee_id=emp.id,
                    manager_id=manager_user.id,
                    proposed_job_level=emp.job_level,
                    current_base=emp.current_base,
                    proposed_base=proposed_base,
                    current_compa_ratio=calculate_compa_ratio(emp.current_base, b_rev.mid_base),
                    proposed_compa_ratio=calculate_compa_ratio(proposed_base, b_rev.mid_base),
                    merit_increase_pct=raise_pct,
                    proposed_bonus_amount=bonus_amt,
                    individual_perf_factor=Decimal("1.10"),
                    company_perf_factor=cycle.company_performance_factor,
                    proposed_equity_gsus=equity_grant,
                    performance_rating=emp.last_performance_rating,
                    status=ReviewStatus.DRAFT,
                    justification_notes="Consistent high impact contributor across infrastructure refactors.",
                )
                db.add(rev)
                await db.flush()

                # Run Agent Audit on first 8 proposals
                if idx < 8:
                    await CycleService.audit_proposal(
                        db, rev.id, actor_email="agent@compflow.internal"
                    )

        # 7. Seed Active Candidate Offers
        recruiter_user = created_users.get(
            "recruiter.infra@compflow.internal", list(created_users.values())[0]
        )
        infra_dept = created_depts["CC-1010-INFRA"]

        sample_offers = [
            (
                "Cassandra Vance",
                "cassandra.vance@gmail.com",
                JobLevel.L5,
                LocationTier.US_ZONE_1,
                Decimal("245000.00"),
                Decimal("25000.00"),
                950,
            ),
            (
                "Marcus Sterling",
                "m.sterling99@yahoo.com",
                JobLevel.L6,
                LocationTier.US_ZONE_1,
                Decimal("320000.00"),
                Decimal("65000.00"),
                1600,
            ),  # Sign-on > $50k -> VP Exception
            (
                "Lillian Chen",
                "lillian.chen@mit.edu",
                JobLevel.L4,
                LocationTier.US_ZONE_2,
                Decimal("185000.00"),
                Decimal("15000.00"),
                600,
            ),
        ]

        for idx, (c_name, c_email, lvl, geo, base, sign_on, eq_gsus) in enumerate(sample_offers):
            offer_stmt = select(CandidateOffer).where(CandidateOffer.candidate_email == c_email)
            if not (await db.execute(offer_stmt)).scalar_one_or_none():
                b_offer = get_default_salary_band(lvl, JobFamily.SOFTWARE_ENGINEERING, geo)
                totals = calculate_offer_total_comp(
                    base, sign_on, b_offer.target_bonus_pct, eq_gsus
                )
                offer = CandidateOffer(
                    id=uuid.uuid4(),
                    offer_number=f"OFF-2026-000{idx + 1}",
                    candidate_name=c_name,
                    candidate_email=c_email,
                    job_level=lvl,
                    job_family=JobFamily.SOFTWARE_ENGINEERING,
                    location_tier=geo,
                    department_id=infra_dept.id,
                    recruiter_id=recruiter_user.id,
                    hiring_manager_id=manager_user.id,
                    proposed_base=base,
                    sign_on_bonus=sign_on,
                    proposed_equity_gsus=eq_gsus,
                    compa_ratio=calculate_compa_ratio(base, b_offer.mid_base),
                    total_target_cash=totals["total_target_cash"],
                    first_year_total_comp=totals["first_year_total_comp"],
                    target_start_date=date.today() + timedelta(days=30),
                    status=OfferStatus.OFFER_DRAFT,
                    notes="Strong distributed systems background from top tier cloud provider.",
                )
                db.add(offer)
                await db.flush()

                # Audit Offer
                await OfferService.audit_offer(db, offer.id, actor_email="agent@compflow.internal")

        await db.commit()
        logger.info(
            "Successfully seeded CompFlow with 60 employees, 3 departments, salary bands, active cycle, and candidate offers."
        )

    finally:
        if owns_session:
            await db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_enterprise_data())
