import datetime as dt

import fastapi as fa
from fastapi.encoders import jsonable_encoder as to_json

from billing.models import Account, ExternalInvoice, Transaction
from billing.serializers import LastDayMetrics


def create_lastday_metrics(request: fa.Request) -> LastDayMetrics:
    date = dt.datetime.combine(dt.date.today(), dt.datetime.min.time())
    total_amount_gained: float = 0.0
    for transaction_document in request.app.db[Transaction.__name__].find(
        {
            "created_at": {"$gte": date.isoformat()},
            "$or": [
                {"account_from": request.app.system_account_id},
                {"account_to": request.app.system_account_id},
            ],
        }
    ):
        transaction = Transaction(**transaction_document)
        if transaction.account_from == request.app.system_account_id:
            total_amount_gained -= transaction.amount
        elif transaction.account_to == request.app.system_account_id:
            total_amount_gained += transaction.amount

    return LastDayMetrics(date=date, total_amount_gained=total_amount_gained)


def create_payroll(request: fa.Request) -> None:
    system_account = Account(
        **request.app.db[Account.__name__].find_one(
            {"user_id": request.app.system_account_id}
        )
    )
    for account_document in request.app.db[Account.__name__].find(
        {"user_id": {"$not": {"$regex": request.app.system_account_id}}}
    ):
        account = Account(**account_document)

        if account.balance < 1e-2:
            # negative balance is carried over
            continue

        amount = account.balance
        invoice = ExternalInvoice(
            user_id=account.user_id, created_at=dt.datetime.now(), amount=amount
        )
        system_account.balance -= amount  # TODO: not sure how to update this

        request.app.db[ExternalInvoice.__name__].insert_one(to_json(invoice))
        request.app.db[Account.__name__].update_one(
            {"user_id": account.user_id}, {"$set": {"balance": 0.0}}
        )
        request.app.db[Account.__name__].update_one(
            {"user_id": system_account.user_id},
            {"$set": {"balance": system_account.balance}},
        )
