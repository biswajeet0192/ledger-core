from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import Base, engine, get_db
from api import accounts, transactions
from models import LedgerEvent, Account, Transaction

app = FastAPI(title="Ledger Core", description="Event-sourced double-entry ledger", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(transactions.router)


@app.on_event("startup")
def on_startup():
    # For local/dev use. In real deployments, use Alembic migrations instead
    # (see migrations/ folder) so schema changes are tracked and reversible.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/monitor/feed")
def recent_activity(limit: int = 50, db: Session = Depends(get_db)):
    """Powers the frontend's live activity feed: latest events across every
    account, newest first, joined with account owner names for readability."""
    rows = (
        db.query(LedgerEvent, Account.owner_name)
        .join(Account, Account.id == LedgerEvent.account_id)
        .order_by(desc(LedgerEvent.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(event.id),
            "account_id": str(event.account_id),
            "owner_name": owner_name,
            "transaction_id": str(event.transaction_id),
            "version": event.version,
            "event_type": event.event_type.value,
            "amount": str(event.amount),
            "created_at": event.created_at.isoformat(),
        }
        for event, owner_name in rows
    ]


@app.get("/monitor/summary")
def summary(db: Session = Depends(get_db)):
    """Powers the dashboard's top-line stats."""
    total_accounts = db.query(Account).count()
    total_transactions = db.query(Transaction).count()
    total_events = db.query(LedgerEvent).count()
    return {
        "total_accounts": total_accounts,
        "total_transactions": total_transactions,
        "total_events": total_events,
    }