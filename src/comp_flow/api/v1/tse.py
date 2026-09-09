"""Technical Solutions Engineer (TSE) Incident Triage & Cryptographic Ledger Endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.database import get_db
from comp_flow.core.ledger import SoxLedgerService
from comp_flow.core.security import get_current_user
from comp_flow.domain.entities import SoxLedgerEntry, User
from comp_flow.domain.models import (
    LedgerVerificationResult,
    SoxLedgerEntryResponse,
    TseDiagnosticReport,
    TseDiagnosticRequest,
)
from comp_flow.service.tse_triage import TseIncidentTriageService

router = APIRouter(prefix="/tse", tags=["TSE Incident Triage & SOX Ledger"])


@router.post("/diagnose", response_model=TseDiagnosticReport)
async def diagnose_incident(
    req: TseDiagnosticRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TseDiagnosticReport:
    """Diagnoses compensation anomalies, correlates trace IDs, and audits cryptographic chain."""
    return await TseIncidentTriageService.diagnose(
        db=db,
        trace_id=req.trace_id,
        review_id=req.review_id,
        offer_id=req.offer_id,
    )


@router.get("/ledger/verify", response_model=LedgerVerificationResult)
async def verify_ledger_integrity(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LedgerVerificationResult:
    """Performs end-to-end cryptographic verification of the SOX Section 404 audit ledger."""
    return await SoxLedgerService.verify_chain(db)


@router.get("/ledger/entries", response_model=list[SoxLedgerEntryResponse])
async def list_ledger_entries(
    entity_id: uuid.UUID | None = Query(default=None, description="Filter by entity UUID"),
    trace_id: str | None = Query(default=None, description="Filter by W3C trace ID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SoxLedgerEntry]:
    """Retrieves chronological immutable SOX ledger blocks with Merkle hashes and signatures."""
    if entity_id:
        return await SoxLedgerService.get_entries_for_entity(db, entity_id)
    if trace_id:
        return await SoxLedgerService.get_entries_by_trace_id(db, trace_id)
    # Default to recent entries
    from sqlalchemy import select

    stmt = select(SoxLedgerEntry).order_by(SoxLedgerEntry.sequence_id.desc()).limit(100)
    res = await db.execute(stmt)
    return list(res.scalars().all())
