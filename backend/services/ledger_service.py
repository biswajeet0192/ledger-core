"""
Core ledger engine.

Golden rules enforced here:
1. Balances are NEVER stored/updated directly. They are derived by replaying
   ledger_events for an account (optionally starting from a snapshot).
2. Every transaction's ledger_entries must sum to zero (double-entry).
3. Concurrent writers to the same account are serialized with
   `SELECT ... FOR UPDATE` row locks so two simultaneous withdrawals can
   never both read a stale balance and overdraw the account.
"""
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from models import (
    Account, LedgerEvent, LedgerEntry, Transaction,
    EventType, TransactionStatus, AccountSnapshot,
)


class InsufficientFundsError(Exception):
    pass


class InvariantViolationError(Exception):
    """Raised if double-entry rows for a transaction don't net to zero."""
    pass


class IdempotentReplay(Exception):
    """Raised (and caught by the API layer) when a request with a previously
    seen idempotency_key comes in again -- we return the original result."""
    def __init__(self, transaction_id: uuid.UUID):
        self.transaction_id = transaction_id


def _lock_account(db: Session, account_id: uuid.UUID) -> Account:
    """Acquire a row-level lock on the account so no other transaction can
    read/write it until this DB transaction commits or rolls back."""
    stmt = select(Account).where(Account.id == account_id).with_for_update()
    account = db.execute(stmt).scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account {account_id} not found")
    return account


def get_balance(db: Session, account_id: uuid.UUID, as_of: Optional[datetime] = None) -> Decimal:
    """Derive balance by replaying events. If a snapshot exists at or before
    `as_of`, start from there instead of event #1 (Phase 6 optimization)."""
    balance = Decimal("0")
    start_version = 0

    snap_q = db.query(AccountSnapshot).filter(AccountSnapshot.account_id == account_id)
    if as_of:
        snap_q = snap_q.filter(AccountSnapshot.created_at <= as_of)
    snapshot = snap_q.order_by(AccountSnapshot.last_event_version.desc()).first()
    if snapshot:
        balance = snapshot.balance
        start_version = snapshot.last_event_version

    q = db.query(LedgerEvent).filter(
        LedgerEvent.account_id == account_id,
        LedgerEvent.version > start_version,
    )
    if as_of:
        q = q.filter(LedgerEvent.created_at <= as_of)
    events = q.order_by(LedgerEvent.version.asc()).all()

    for e in events:
        if e.event_type in (EventType.DEPOSIT, EventType.TRANSFER_IN):
            balance += e.amount
        elif e.event_type in (EventType.WITHDRAWAL, EventType.TRANSFER_OUT):
            balance -= e.amount
        # ACCOUNT_CREATED / TRANSACTION_REVERSED handled elsewhere / no-op here

    return balance


def _next_version(db: Session, account: Account) -> int:
    account.version += 1
    return account.version


def _append_event(db: Session, account: Account, txn: Transaction,
                   event_type: EventType, amount: Decimal, metadata: dict = None) -> LedgerEvent:
    event = LedgerEvent(
        account_id=account.id,
        transaction_id=txn.id,
        version=_next_version(db, account),
        event_type=event_type,
        amount=amount,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event


def _check_idempotency(db: Session, idempotency_key: Optional[str]) -> Optional[Transaction]:
    if not idempotency_key:
        return None
    return db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).first()


def create_account(db: Session, owner_name: str, account_type: str, currency: str) -> Account:
    account = Account(owner_name=owner_name, account_type=account_type, currency=currency, version=0)
    db.add(account)
    db.flush()

    txn = Transaction(status=TransactionStatus.COMPLETED, description="account opened")
    db.add(txn)
    db.flush()

    _append_event(db, account, txn, EventType.ACCOUNT_CREATED, Decimal("0"))
    db.commit()
    db.refresh(account)
    return account


def deposit(db: Session, account_id: uuid.UUID, amount: Decimal,
            idempotency_key: Optional[str] = None, description: Optional[str] = None) -> Transaction:
    existing = _check_idempotency(db, idempotency_key)
    if existing:
        return existing

    account = _lock_account(db, account_id)

    txn = Transaction(status=TransactionStatus.PENDING, idempotency_key=idempotency_key, description=description)
    db.add(txn)
    db.flush()

    # Double entry: cash reserve (external world) credits, user account debits
    # in the bank's own books; from the user's point of view amount is +amount.
    db.add(LedgerEntry(transaction_id=txn.id, account_id=account.id, debit=Decimal("0"), credit=amount))

    _append_event(db, account, txn, EventType.DEPOSIT, amount)

    _assert_entries_balance(db, txn.id)
    txn.status = TransactionStatus.COMPLETED
    db.commit()
    db.refresh(txn)
    return txn


def withdraw(db: Session, account_id: uuid.UUID, amount: Decimal,
             idempotency_key: Optional[str] = None, description: Optional[str] = None) -> Transaction:
    existing = _check_idempotency(db, idempotency_key)
    if existing:
        return existing

    account = _lock_account(db, account_id)  # blocks concurrent withdrawals on same account
    current_balance = get_balance(db, account_id)
    if current_balance < amount:
        raise InsufficientFundsError(
            f"Account {account_id} has balance {current_balance}, cannot withdraw {amount}"
        )

    txn = Transaction(status=TransactionStatus.PENDING, idempotency_key=idempotency_key, description=description)
    db.add(txn)
    db.flush()

    db.add(LedgerEntry(transaction_id=txn.id, account_id=account.id, debit=amount, credit=Decimal("0")))

    _append_event(db, account, txn, EventType.WITHDRAWAL, amount)

    _assert_entries_balance(db, txn.id)
    txn.status = TransactionStatus.COMPLETED
    db.commit()
    db.refresh(txn)
    return txn


def transfer(db: Session, source_account_id: uuid.UUID, destination_account_id: uuid.UUID,
             amount: Decimal, idempotency_key: Optional[str] = None,
             description: Optional[str] = None) -> Transaction:
    existing = _check_idempotency(db, idempotency_key)
    if existing:
        return existing

    if source_account_id == destination_account_id:
        raise ValueError("source_account and destination_account must differ")

    # Always lock accounts in a fixed order (sorted by UUID) to avoid deadlocks
    # when two transfers move money between the same pair of accounts in
    # opposite directions concurrently.
    ids_in_order = sorted([source_account_id, destination_account_id], key=str)
    locked = {aid: _lock_account(db, aid) for aid in ids_in_order}
    source = locked[source_account_id]
    destination = locked[destination_account_id]

    current_balance = get_balance(db, source_account_id)
    if current_balance < amount:
        raise InsufficientFundsError(
            f"Account {source_account_id} has balance {current_balance}, cannot transfer {amount}"
        )

    txn = Transaction(status=TransactionStatus.PENDING, idempotency_key=idempotency_key, description=description)
    db.add(txn)
    db.flush()

    db.add(LedgerEntry(transaction_id=txn.id, account_id=source.id, debit=amount, credit=Decimal("0")))
    db.add(LedgerEntry(transaction_id=txn.id, account_id=destination.id, debit=Decimal("0"), credit=amount))

    _append_event(db, source, txn, EventType.TRANSFER_OUT, amount, {"counterparty": str(destination.id)})
    _append_event(db, destination, txn, EventType.TRANSFER_IN, amount, {"counterparty": str(source.id)})

    _assert_entries_balance(db, txn.id)
    txn.status = TransactionStatus.COMPLETED
    db.commit()
    db.refresh(txn)
    return txn


def _assert_entries_balance(db: Session, transaction_id: uuid.UUID) -> None:
    """Enforces SUM(credit) - SUM(debit) == 0 for a transaction before commit."""
    entries = db.query(LedgerEntry).filter(LedgerEntry.transaction_id == transaction_id).all()
    total = sum((e.credit - e.debit) for e in entries)
    if total != Decimal("0"):
        raise InvariantViolationError(
            f"Ledger entries for transaction {transaction_id} do not net to zero (got {total})"
        )


def get_events(db: Session, account_id: uuid.UUID, limit: int = 200):
    return (
        db.query(LedgerEvent)
        .filter(LedgerEvent.account_id == account_id)
        .order_by(LedgerEvent.version.desc())
        .limit(limit)
        .all()
    )


def get_audit_trail(db: Session, account_id: uuid.UUID):
    balance = get_balance(db, account_id)
    events = get_events(db, account_id, limit=500)
    return balance, events


def create_snapshot(db: Session, account_id: uuid.UUID) -> AccountSnapshot:
    """Phase 6: freeze current derived balance so future replays start here."""
    account = db.query(Account).filter(Account.id == account_id).one()
    balance = get_balance(db, account_id)
    snap = AccountSnapshot(account_id=account_id, balance=balance, last_event_version=account.version)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap