"""Tests for SOX Section 404 Cryptographic Audit Ledger Subsystem."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.ledger import (
    GENESIS_PREVIOUS_HASH,
    SoxLedgerService,
    canonical_json,
    hash_payload,
)
from comp_flow.domain.entities import SoxLedgerEntry


@pytest.mark.asyncio
async def test_canonical_json_determinism() -> None:
    """Verifies that dictionary key order and formatting do not alter canonical hash."""
    d1 = {
        "b_val": Decimal("150000.00"),
        "a_val": "Engineering",
        "nested": {"z": 1, "a": 2},
    }
    d2 = {
        "a_val": "Engineering",
        "nested": {"a": 2, "z": 1},
        "b_val": Decimal("150000.00"),
    }
    assert canonical_json(d1) == canonical_json(d2)
    assert hash_payload(d1) == hash_payload(d2)


@pytest.mark.asyncio
async def test_sox_ledger_chain_creation_and_verification(
    test_db_session: AsyncSession,
) -> None:
    """Verifies that sequential ledger blocks correctly chain previous hashes and pass verification."""
    db = test_db_session
    entity_id_1 = uuid.uuid4()
    entity_id_2 = uuid.uuid4()

    # Block 1
    e1 = await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id_1,
        action="PROPOSAL_SUBMITTED",
        actor_email="manager@compflow.internal",
        payload={"proposed_base": "180000.00", "notes": "Top performer"},
        trace_id="trace_0001",
    )
    assert e1.sequence_id == 1
    assert e1.previous_hash == GENESIS_PREVIOUS_HASH
    assert e1.block_hash is not None
    assert e1.signature is not None

    # Block 2
    e2 = await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id_1,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={"decision": "AUTO_APPROVED", "compa_ratio": "1.05"},
        trace_id="trace_0002",
    )
    assert e2.sequence_id == 2
    assert e2.previous_hash == e1.block_hash

    # Block 3
    e3 = await SoxLedgerService.record_entry(
        db=db,
        entity_type="CANDIDATE_OFFER",
        entity_id=entity_id_2,
        action="OFFER_AUDIT",
        actor_email="system@compflow.internal",
        payload={"decision": "OFFER_APPROVED", "sign_on_bonus": "20000.00"},
        trace_id="trace_0003",
    )
    assert e3.sequence_id == 3
    assert e3.previous_hash == e2.block_hash

    # Verify the untouched chain
    res = await SoxLedgerService.verify_chain(db)
    assert res.is_valid is True
    assert res.status == "SECURE"
    assert res.total_entries == 3
    assert res.genesis_hash == e1.block_hash
    assert res.head_hash == e3.block_hash
    assert res.tampered_sequence_id is None


@pytest.mark.asyncio
async def test_sox_ledger_detects_payload_tampering(
    test_db_session: AsyncSession,
) -> None:
    """Verifies that directly modifying payload data in the database is detected immediately."""
    db = test_db_session
    entity_id = uuid.uuid4()

    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={"proposed_base": "150000.00", "decision": "AUTO_APPROVED"},
    )
    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id,
        action="VP_APPROVAL",
        actor_email="vp@compflow.internal",
        payload={"notes": "Approved standard merit"},
    )

    # Maliciously alter payload of block 1 directly in database
    await db.execute(
        update(SoxLedgerEntry)
        .where(SoxLedgerEntry.sequence_id == 1)
        .values(payload={"proposed_base": "250000.00", "decision": "AUTO_APPROVED"})
    )
    await db.flush()

    # Verification must flag tampering
    res = await SoxLedgerService.verify_chain(db)
    assert res.is_valid is False
    assert res.status == "COMPROMISED"
    assert res.tampered_sequence_id == 1
    assert "Payload tampering detected" in str(res.error_reason)


@pytest.mark.asyncio
async def test_sox_ledger_detects_broken_hash_chain(
    test_db_session: AsyncSession,
) -> None:
    """Verifies that altering previous_hash is caught by chain verification."""
    db = test_db_session
    entity_id = uuid.uuid4()

    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id,
        action="PROPOSAL_SUBMITTED",
        actor_email="mgr@compflow.internal",
        payload={"base": "120000"},
    )
    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id,
        action="AGENT_AUDIT",
        actor_email="system@compflow.internal",
        payload={"decision": "AUTO_APPROVED"},
    )

    # Maliciously alter previous_hash of block 2
    fake_hash = "f" * 64
    await db.execute(
        update(SoxLedgerEntry)
        .where(SoxLedgerEntry.sequence_id == 2)
        .values(previous_hash=fake_hash)
    )
    await db.flush()

    res = await SoxLedgerService.verify_chain(db)
    assert res.is_valid is False
    assert res.status == "COMPROMISED"
    assert res.tampered_sequence_id == 2
    assert "Hash chain broken" in str(res.error_reason)


@pytest.mark.asyncio
async def test_sox_ledger_detects_forged_signature(
    test_db_session: AsyncSession,
) -> None:
    """Verifies that modifying a block's HMAC signature fails verification."""
    db = test_db_session
    entity_id = uuid.uuid4()

    await SoxLedgerService.record_entry(
        db=db,
        entity_type="EMPLOYEE_REVIEW",
        entity_id=entity_id,
        action="PROPOSAL_SUBMITTED",
        actor_email="mgr@compflow.internal",
        payload={"base": "120000"},
    )

    # Forgery: substitute fake signature
    await db.execute(
        update(SoxLedgerEntry).where(SoxLedgerEntry.sequence_id == 1).values(signature="0" * 64)
    )
    await db.flush()

    res = await SoxLedgerService.verify_chain(db)
    assert res.is_valid is False
    assert res.status == "COMPROMISED"
    assert res.tampered_sequence_id == 1
    assert "signature" in str(res.error_reason).lower()
