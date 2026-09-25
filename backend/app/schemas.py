from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime


class TransactionBase(BaseModel):
    title: str = Field(..., example="Coffee")
    amount: float = Field(..., gt=0, example=350.0)
    category: Optional[str] = Field(None, example="Groceries")
    notes: Optional[str] = None
    date: Optional[datetime] = None
    kind: Literal["expense", "income", "investment"] = "expense"
    payment_method: Optional[str] = Field(None, example="UPI")
    merchant: Optional[str] = None
    recurring: bool = False


class TransactionCreate(TransactionBase):
    pass


class TransactionOut(TransactionBase):
    id: str

    model_config = {"from_attributes": True}


class AccountCreate(BaseModel):
    name: str
    account_type: str = "savings"
    institution: Optional[str] = None
    opening_balance: float = 0


class BudgetCreate(BaseModel):
    name: str
    category: Optional[str] = None
    amount: float = Field(..., gt=0)
    period: str = "monthly"


class GoalCreate(BaseModel):
    name: str
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(0, ge=0)
    target_date: Optional[str] = None


class BillCreate(BaseModel):
    name: str
    amount: float = Field(..., gt=0)
    due_date: str
    frequency: str = "monthly"
    status: str = "upcoming"


class SMSParseRequest(BaseModel):
    text: str


class SMSParseResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class BatchTransactionCreate(BaseModel):
    transactions: list[TransactionCreate]


class SyncWebhookPayload(BaseModel):
    text: Optional[str] = None
    sender: Optional[str] = None
    timestamp: Optional[str] = None


# --- RBI Account Aggregator (AA) Models (ReBIT Specifications) ---

class AAConsentRequest(BaseModel):
    fip_id: str = Field(..., example="FIP-HDFC")
    mobile_number: str = Field(..., example="9876543210")
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    consent_mode: str = "STORE"
    fetch_type: str = "PERIODIC"


class AAOtpVerifyRequest(BaseModel):
    consent_handle: str
    otp: str


class AADataFetchRequest(BaseModel):
    consent_id: str
    fip_id: str
    account_ids: Optional[List[str]] = None


class StatementUploadResponse(BaseModel):
    success: bool
    bank_detected: str
    total_parsed: int
    created_count: int
    skipped_count: int
    transactions: List[Dict[str, Any]]
    account_summary: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
