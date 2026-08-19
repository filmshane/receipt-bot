from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class Category(str, Enum):
    TRAVEL = "Travel"
    FOOD = "Food"
    EQUIPMENT = "Equipment"
    OTHER = "Other"

    @classmethod
    def coerce(cls, value: Any) -> "Category":
        if isinstance(value, cls):
            return value
        if value is None or value == "":
            return cls.OTHER
        s = str(value).strip().lower()
        mapping = {
            "travel": cls.TRAVEL,
            "food": cls.FOOD,
            "meal": cls.FOOD,
            "meals": cls.FOOD,
            "dining": cls.FOOD,
            "equipment": cls.EQUIPMENT,
            "gear": cls.EQUIPMENT,
            "hardware": cls.EQUIPMENT,
            "other": cls.OTHER,
        }
        if s in mapping:
            return mapping[s]
        for c in cls:
            if c.value.lower() == s:
                return c
        return cls.OTHER


class ExpenseRow(BaseModel):
    telegram_user_id: int
    telegram_username: str = ""
    receipt_file_id: str = ""
    vendor: str = ""
    expense_date: str  # YYYY-MM-DD
    currency: str = "USD"
    total: float
    tax: float = 0.0
    category: Category = Category.OTHER
    notes: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_review: bool = False
    message_id: int
    cfo_email_sent_at: str = ""
    threshold: float = Field(default=500.0, exclude=True)

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, v: Any) -> Category:
        return Category.coerce(v)

    @field_validator("expense_date", mode="before")
    @classmethod
    def _date(cls, v: Any) -> str:
        if v is None or v == "":
            return date.today().isoformat()
        if isinstance(v, datetime):
            return v.date().isoformat()
        if isinstance(v, date):
            return v.isoformat()
        s = str(v).strip()
        # try common formats
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s[:10], fmt).date().isoformat()
            except ValueError:
                continue
        return s[:10]

    @field_validator("total", "tax", mode="before")
    @classmethod
    def _num(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace(",", "").replace("$", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    @property
    def over_500(self) -> bool:
        return float(self.total) > float(self.threshold)

    def to_excel_row(self) -> List[Any]:
        return [
            self.telegram_user_id,
            self.telegram_username,
            self.receipt_file_id,
            self.vendor,
            self.expense_date,
            self.currency,
            self.total,
            self.tax,
            self.category.value,
            self.notes,
            self.confidence,
            "TRUE" if self.needs_review else "FALSE",
            self.message_id,
            "TRUE" if self.over_500 else "FALSE",
            self.cfo_email_sent_at or "",
        ]


class ExtractionResult(BaseModel):
    is_receipt: bool = True
    vendor: str = ""
    expense_date: Optional[str] = None
    currency: str = "USD"
    total: Optional[float] = None
    tax: Optional[float] = None
    category: Category = Category.OTHER
    notes: str = ""
    confidence: float = 0.0
    error: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, v: Any) -> Category:
        return Category.coerce(v)
