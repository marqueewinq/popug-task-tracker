from uuid import uuid4
import datetime as dt

from pydantic import BaseModel, Field


class Issue(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    issue_id: str
    assignee_id: str

    marked_as_done: bool = False

    cost_for_assign: float
    cost_for_done: float


class Account(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    user_id: str

    # in case of multiple currencies, they can be a separate table with FK to Account
    balance: float


class Transaction(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    account_from: str
    account_to: str
    description: str

    created_at: dt.datetime

    amount: float


class ExternalInvoice(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    user_id: str

    created_at: dt.datetime

    amount: float
