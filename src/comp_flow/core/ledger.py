"""Cryptographic SOX Section 404 Immutable Audit Ledger Subsystem.

Provides hash-chained Merkle blocks with canonical JSON serialization, SHA-256 payload
digests, previous block linking, and HMAC-SHA256 non-repudiation signatures.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from comp_flow.core.config import settings
from comp_flow.core.tracing import get_current_trace_id
from comp_flow.domain.entities import SoxLedgerEntry
from comp_flow.domain.models import LedgerVerificationResult

logger = logging.getLogger(__name__)

GENESIS_PREVIOUS_HASH: str = "0" * 64


def _serialize_for_canonical_json(val: Any) -> Any:
    """Recursively converts datatypes (UUID, Decimal, datetime, date) for canonical serialization."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (list, tuple, set)):
        return [_serialize_for_canonical_json(item) for item in val]
    if isinstance(val, dict):
        return {str(k): _serialize_for_canonical_json(v) for k, v in val.items()}
    return val


def canonical_json(data: dict[str, Any]) -> str:
    """Serializes dictionary to deterministic canonical JSON representation (RFC 8785 subset)."""
    cleaned = _serialize_for_canonical_json(data)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def format_timestamp(dt: datetime) -> str:
    """Formats datetime into deterministic UTC string: YYYY-MM-DDTHH:MM:SSZ."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_sha256(data: str) -> str:
    """Computes hex-encoded SHA-256 digest of input string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def hash_payload(payload: dict[str, Any]) -> str:
    """Computes SHA-256 hash of canonical JSON serialized payload."""
    return compute_sha256(canonical_json(payload))


def compute_block_hash(
    sequence_id: int,
    timestamp_iso: str,
    trace_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_email: str,
    payload_hash: str,
    previous_hash: str,
) -> str:
    """Calculates Merkle block hash over sequence, timestamp, trace, identity, and hashes."""
    header_string = (
        f"{sequence_id}:{timestamp_iso}:{trace_id}:{entity_type}:"
        f"{entity_id}:{action}:{actor_email}:{payload_hash}:{previous_hash}"
    )
    return compute_sha256(header_string)


def sign_block(block_hash: str, secret_key: str | None = None) -> str:
    """Generates HMAC-SHA256 non-repudiation signature for the block hash."""
    key = (secret_key or settings.SECRET_KEY).encode("utf-8")
    return hmac.new(key, block_hash.encode("utf-8"), hashlib.sha256).hexdigest()


class SoxLedgerService:
    """Enterprise Cryptographic Audit Ledger Engine."""

    @classmethod
    async def record_entry(
        cls,
        db: AsyncSession,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_email: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> SoxLedgerEntry:
        """Appends a new cryptographically sealed, hash-chained entry to the SOX audit ledger."""
        effective_trace_id = trace_id or get_current_trace_id() or "0" * 32
        timestamp = datetime.now(UTC)

        # Retrieve highest sequence number and previous block hash
        stmt = select(SoxLedgerEntry).order_by(SoxLedgerEntry.sequence_id.desc()).limit(1)
        res = await db.execute(stmt)
        last_entry = res.scalars().first()

        if last_entry is None:
            previous_hash = GENESIS_PREVIOUS_HASH
            next_sequence_id = 1
        else:
            previous_hash = last_entry.block_hash
            next_sequence_id = last_entry.sequence_id + 1

        p_hash = hash_payload(payload)
        ts_str = format_timestamp(timestamp)
        b_hash = compute_block_hash(
            sequence_id=next_sequence_id,
            timestamp_iso=ts_str,
            trace_id=effective_trace_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            actor_email=actor_email,
            payload_hash=p_hash,
            previous_hash=previous_hash,
        )
        signature = sign_block(b_hash)

        entry = SoxLedgerEntry(
            sequence_id=next_sequence_id,
            timestamp=timestamp,
            trace_id=effective_trace_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_email=actor_email,
            payload=payload,
            payload_hash=p_hash,
            previous_hash=previous_hash,
            block_hash=b_hash,
            signature=signature,
        )
        db.add(entry)
        await db.flush()

        logger.info(
            f"SOX Ledger Entry #{next_sequence_id} sealed [{action}] for {entity_type}:{entity_id} (hash={b_hash[:12]}...)"
        )
        return entry

    @classmethod
    async def verify_chain(
        cls,
        db: AsyncSession,
        limit: int | None = None,
    ) -> LedgerVerificationResult:
        """Verifies the complete cryptographic integrity of the SOX audit ledger."""
        stmt = select(SoxLedgerEntry).order_by(SoxLedgerEntry.sequence_id.asc())
        if limit:
            stmt = stmt.limit(limit)
        res = await db.execute(stmt)
        entries = list(res.scalars().all())

        now = datetime.now(UTC)
        if not entries:
            return LedgerVerificationResult(
                is_valid=True,
                status="SECURE",
                total_entries=0,
                verified_at=now,
            )

        expected_prev_hash = GENESIS_PREVIOUS_HASH
        expected_seq = 1

        for entry in entries:
            # 1. Verify sequence continuity (detect deleted blocks)
            if entry.sequence_id != expected_seq:
                return LedgerVerificationResult(
                    is_valid=False,
                    status="COMPROMISED",
                    total_entries=len(entries),
                    tampered_sequence_id=entry.sequence_id,
                    tampered_entry_id=entry.entry_id,
                    error_reason=(
                        f"Sequence discontinuity detected: expected #{expected_seq}, "
                        f"found #{entry.sequence_id} (potential block deletion)"
                    ),
                    verified_at=now,
                )

            # 2. Verify previous hash chaining (detect insertion or severance)
            if entry.previous_hash != expected_prev_hash:
                return LedgerVerificationResult(
                    is_valid=False,
                    status="COMPROMISED",
                    total_entries=len(entries),
                    tampered_sequence_id=entry.sequence_id,
                    tampered_entry_id=entry.entry_id,
                    error_reason=(
                        f"Hash chain broken at sequence #{entry.sequence_id}: "
                        f"previous_hash does not match preceding block hash"
                    ),
                    verified_at=now,
                )

            # 3. Verify payload hash integrity (detect altered data)
            recalculated_p_hash = hash_payload(entry.payload)
            if recalculated_p_hash != entry.payload_hash:
                return LedgerVerificationResult(
                    is_valid=False,
                    status="COMPROMISED",
                    total_entries=len(entries),
                    tampered_sequence_id=entry.sequence_id,
                    tampered_entry_id=entry.entry_id,
                    error_reason=(
                        f"Payload tampering detected at sequence #{entry.sequence_id}: "
                        f"expected hash {recalculated_p_hash[:16]}..., recorded {entry.payload_hash[:16]}..."
                    ),
                    verified_at=now,
                )

            # 4. Verify block hash calculation
            ts_str = format_timestamp(entry.timestamp)
            recalculated_b_hash = compute_block_hash(
                sequence_id=entry.sequence_id,
                timestamp_iso=ts_str,
                trace_id=entry.trace_id,
                entity_type=entry.entity_type,
                entity_id=str(entry.entity_id),
                action=entry.action,
                actor_email=entry.actor_email,
                payload_hash=entry.payload_hash,
                previous_hash=entry.previous_hash,
            )
            if recalculated_b_hash != entry.block_hash:
                return LedgerVerificationResult(
                    is_valid=False,
                    status="COMPROMISED",
                    total_entries=len(entries),
                    tampered_sequence_id=entry.sequence_id,
                    tampered_entry_id=entry.entry_id,
                    error_reason=(
                        f"Block header tampering detected at sequence #{entry.sequence_id}: "
                        f"block hash mismatch"
                    ),
                    verified_at=now,
                )

            # 5. Verify cryptographic HMAC signature (detect unauthorized forging)
            expected_sig = sign_block(entry.block_hash)
            if not hmac.compare_digest(entry.signature, expected_sig):
                return LedgerVerificationResult(
                    is_valid=False,
                    status="COMPROMISED",
                    total_entries=len(entries),
                    tampered_sequence_id=entry.sequence_id,
                    tampered_entry_id=entry.entry_id,
                    error_reason=(
                        f"Cryptographic signature invalid at sequence #{entry.sequence_id}: "
                        f"signature does not match platform secret key"
                    ),
                    verified_at=now,
                )

            expected_prev_hash = entry.block_hash
            expected_seq += 1

        return LedgerVerificationResult(
            is_valid=True,
            status="SECURE",
            total_entries=len(entries),
            genesis_hash=entries[0].block_hash,
            head_hash=entries[-1].block_hash,
            verified_at=now,
        )

    @classmethod
    async def get_entries_for_entity(
        cls, db: AsyncSession, entity_id: UUID
    ) -> list[SoxLedgerEntry]:
        """Fetches chronological audit trail of ledger blocks for a specific entity."""
        stmt = (
            select(SoxLedgerEntry)
            .where(SoxLedgerEntry.entity_id == entity_id)
            .order_by(SoxLedgerEntry.sequence_id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @classmethod
    async def get_entries_by_trace_id(cls, db: AsyncSession, trace_id: str) -> list[SoxLedgerEntry]:
        """Fetches ledger blocks associated with an OpenTelemetry trace context."""
        stmt = (
            select(SoxLedgerEntry)
            .where(SoxLedgerEntry.trace_id == trace_id)
            .order_by(SoxLedgerEntry.sequence_id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())
