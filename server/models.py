"""Validated, provider-independent records. Money never passes through binary floats."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocumentKind = Literal["invoice", "purchase_order", "delivery"]


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(ge=0, le=1000000)
    unit_price: Decimal | None = Field(default=None, ge=0, le=100000000)
    amount: Decimal | None = Field(default=None, ge=0, le=1000000000)

    @field_validator("quantity", "unit_price", "amount")
    @classmethod
    def finite_decimal(cls, value):
        if value is not None and not value.is_finite():
            raise ValueError("Values must be finite")
        return value


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: DocumentKind
    supplier: str = Field(min_length=1, max_length=200)
    number: str = Field(min_length=1, max_length=100)
    po_number: str = Field(min_length=1, max_length=100)
    date: date
    currency: Literal["USD", "EUR", "GBP", "INR", "CAD", "AUD"] = "USD"
    subtotal: Decimal | None = Field(default=None, ge=0, le=1000000000)
    tax: Decimal | None = Field(default=None, ge=0, le=1000000000)
    total: Decimal | None = Field(default=None, ge=0, le=1000000000)
    line_items: list[LineItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def financial_values(self):
        if self.kind != "delivery":
            if self.total is None or self.subtotal is None or self.tax is None:
                raise ValueError("Financial documents need subtotal, tax, and total")
            if any(line.unit_price is None or line.amount is None for line in self.line_items):
                raise ValueError("Financial line items need unit price and amount")
        return self


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=120)
    value: str = Field(max_length=500)
    reason: str = Field(min_length=3, max_length=1000)
    expected_revision: int = Field(ge=1)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "reject"]
    note: str = Field(min_length=3, max_length=2000)
    expected_revision: int = Field(ge=1)


def set_path(record: dict, path: str, value: str) -> dict:
    """Only edit existing scalar record fields; validate the entire resulting record."""
    import copy
    import re

    allowed = {"supplier", "number", "po_number", "date", "currency", "subtotal", "tax", "total"}
    updated = copy.deepcopy(record)
    if path in allowed:
        updated[path] = value
    elif match := re.fullmatch(
        r"line_items\.(\d+)\.(sku|description|quantity|unit_price|amount)", path
    ):
        index, field = int(match[1]), match[2]
        if index >= len(updated.get("line_items", [])):
            raise ValueError("Line item does not exist")
        updated["line_items"][index][field] = value
    else:
        raise ValueError("Only existing extracted fields can be corrected")
    return DocumentRecord.model_validate(updated).model_dump(mode="json")
