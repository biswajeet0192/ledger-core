import uuid
import enum
from sqlalchemy import (
    Column, String, Numeric, DateTime, Integer, ForeignKey, Enum, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from database import Base


def gen_uuid():
    return uuid.uuid4()


class EventType(str, enum.Enum):
    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSACTION_REVERSED = "TRANSACTION_REVERSED"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    owner_name = Column(String, nullable=False)
    account_type = Column(String, nullable=False, default="WALLET")
    currency = Column(String(3), nullable=False, default="INR")
    # version = number of events applied; used for optimistic locking on writes
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    events = relationship("LedgerEvent", back_populates="account", order_by="LedgerEvent.version")


class Transaction(Base):
    """A logical operation (deposit / withdraw / transfer). One transaction can
    fan out into multiple ledger_entries that must sum to zero (double entry)."""
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    idempotency_key = Column(String, unique=True, nullable=True, index=True)
    status = Column(Enum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entries = relationship("LedgerEntry", back_populates="transaction")
    events = relationship("LedgerEvent", back_populates="transaction")


class LedgerEvent(Base):
    """Immutable, append-only fact. Balances are always derived by replaying
    these rows -- never mutated in place."""
    __tablename__ = "ledger_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)  # per-account monotonically increasing
    event_type = Column(Enum(EventType), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    event_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    account = relationship("Account", back_populates="events")
    transaction = relationship("Transaction", back_populates="events")


class LedgerEntry(Base):
    """Double-entry row. For any given transaction_id, SUM(credit) - SUM(debit)
    must equal zero -- enforced in application code before commit."""
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    debit = Column(Numeric(18, 2), nullable=False, default=0)
    credit = Column(Numeric(18, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    transaction = relationship("Transaction", back_populates="entries")


class AccountSnapshot(Base):
    """Optional optimization (Phase 6): cached balance as of a given event
    version, so replay only needs to start from here instead of event #1."""
    __tablename__ = "account_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    balance = Column(Numeric(18, 2), nullable=False)
    last_event_version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())