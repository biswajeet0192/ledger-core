from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import schemas
from services import ledger_service
from services.ledger_service import InsufficientFundsError, InvariantViolationError

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/deposit", response_model=schemas.TransactionOut)
def deposit(payload: schemas.DepositRequest, db: Session = Depends(get_db)):
    try:
        txn = ledger_service.deposit(
            db, payload.account_id, payload.amount, payload.idempotency_key, payload.description
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except InvariantViolationError as e:
        raise HTTPException(500, str(e))
    return schemas.TransactionOut(id=txn.id, status=txn.status, description=txn.description, created_at=txn.created_at)


@router.post("/withdraw", response_model=schemas.TransactionOut)
def withdraw(payload: schemas.WithdrawRequest, db: Session = Depends(get_db)):
    try:
        txn = ledger_service.withdraw(
            db, payload.account_id, payload.amount, payload.idempotency_key, payload.description
        )
    except InsufficientFundsError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except InvariantViolationError as e:
        raise HTTPException(500, str(e))
    return schemas.TransactionOut(id=txn.id, status=txn.status, description=txn.description, created_at=txn.created_at)


@router.post("/transfer", response_model=schemas.TransactionOut)
def transfer(payload: schemas.TransferRequest, db: Session = Depends(get_db)):
    try:
        txn = ledger_service.transfer(
            db,
            payload.source_account,
            payload.destination_account,
            payload.amount,
            payload.idempotency_key,
            payload.description,
        )
    except InsufficientFundsError as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except InvariantViolationError as e:
        raise HTTPException(500, str(e))
    return schemas.TransactionOut(id=txn.id, status=txn.status, description=txn.description, created_at=txn.created_at)