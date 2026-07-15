import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import schemas
from models import Account
from services import ledger_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=schemas.AccountOut, status_code=201)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    account = ledger_service.create_account(
        db, payload.owner_name, payload.account_type, payload.currency
    )
    return account


@router.get("", response_model=List[schemas.AccountOut])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).order_by(Account.created_at.desc()).all()


@router.get("/{account_id}", response_model=schemas.AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    return account


@router.get("/{account_id}/balance", response_model=schemas.BalanceOut)
def get_balance(account_id: uuid.UUID, at: Optional[datetime] = None, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    balance = ledger_service.get_balance(db, account_id, as_of=at)
    return schemas.BalanceOut(account_id=account_id, balance=balance, as_of=at)


@router.get("/{account_id}/events", response_model=List[schemas.EventOut])
def get_events(account_id: uuid.UUID, limit: int = 200, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    return ledger_service.get_events(db, account_id, limit=limit)


@router.get("/{account_id}/audit", response_model=schemas.AuditOut)
def get_audit(account_id: uuid.UUID, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    balance, events = ledger_service.get_audit_trail(db, account_id)
    return schemas.AuditOut(account_id=account_id, current_balance=balance, history=events)


@router.post("/{account_id}/snapshot", status_code=201)
def snapshot_account(account_id: uuid.UUID, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(404, "Account not found")
    snap = ledger_service.create_snapshot(db, account_id)
    return {"account_id": account_id, "balance": snap.balance, "last_event_version": snap.last_event_version}