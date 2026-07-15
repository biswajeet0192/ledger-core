import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Any

from pydantic import BaseModel, Field, ConfigDict


class AccountCreate(BaseModel):
    owner_name: str
    account_type: str = "WALLET"
    currency: str = "INR"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_name: str
    account_type: str
    currency: str
    version: int
    created_at: datetime


class BalanceOut(BaseModel):
    account_id: uuid.UUID
    balance: Decimal
    as_of: Optional[datetime] = None


class DepositRequest(BaseModel):
    account_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    idempotency_key: Optional[str] = None
    description: Optional[str] = None


class WithdrawRequest(BaseModel):
    account_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    idempotency_key: Optional[str] = None
    description: Optional[str] = None


class TransferRequest(BaseModel):
    source_account: uuid.UUID
    destination_account: uuid.UUID
    amount: Decimal = Field(gt=0)
    idempotency_key: Optional[str] = None
    description: Optional[str] = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    account_id: uuid.UUID
    transaction_id: uuid.UUID
    version: int
    event_type: str
    amount: Decimal
    event_metadata: Optional[Any] = None
    created_at: datetime


class TransactionOut(BaseModel):
    id: uuid.UUID
    status: str
    description: Optional[str]
    created_at: datetime
    balance_after_source: Optional[Decimal] = None
    balance_after_destination: Optional[Decimal] = None


class AuditOut(BaseModel):
    account_id: uuid.UUID
    current_balance: Decimal
    history: List[EventOut]