import logging
import os
import random
import sys
import typing as ty
import datetime as dt

from common import topics
from fastapi.encoders import jsonable_encoder as to_json
from pymongo import MongoClient

from billing.models import Account, Issue, Transaction

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]
SYSTEM_ACCOUNT_USER_ID = os.environ["SYSTEM_ACCOUNT_USER_ID"]

KAFKA_PORT = os.environ["KAFKA_PORT"]
KAFKA_SERVER = os.environ["KAFKA_SERVER"]

mongo_url = (
    f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
)

logging.basicConfig(level=logging.INFO)


def replicate_account(data: topics.UserCreatedSchema) -> None:
    db = MongoClient(mongo_url)[DB_NAME]

    if db[Account.__name__].find_one({"user_id": data.user_id}) is not None:
        logging.info(f"Account {data.user_id} already exists")
        return

    account = Account(user_id=data.user_id, balance=0.0)
    db[Account.__name__].insert_one(to_json(account))
    logging.info(f"Created Account {data.user_id}")


def replicate_issue_created(data: topics.IssueAssignedSchema) -> None:
    logging.info(f"\t >> replicate_issue_created({data}")
    db = MongoClient(mongo_url)[DB_NAME]

    if db[Issue.__name__].find_one({"issue_id": data.issue_id}) is not None:
        logging.info(f"Issue {data.issue_id} already exists")
        return

    cost_for_assign = random.random() * 10 + 10
    cost_for_done = random.random() * 20 + 20

    issue = Issue(
        **data.dict(), cost_for_assign=cost_for_assign, cost_for_done=cost_for_done
    )
    account = Account(**db[Account.__name__].find_one({"user_id": data.assignee_id}))
    system_account = Account(
        **db[Account.__name__].find_one({"user_id": SYSTEM_ACCOUNT_USER_ID})
    )
    transaction = Transaction(
        account_from=account.user_id,
        account_to=SYSTEM_ACCOUNT_USER_ID,
        description=f"Issue {issue.issue_id} assigned to you",
        created_at=dt.datetime.utcnow(),
        amount=cost_for_assign,
    )
    account.balance -= cost_for_assign
    system_account.balance += cost_for_assign

    # TODO: with atomic commit
    db[Account.__name__].update_one(
        {"_id": account.uuid}, {"$set": {"balance": account.balance}}
    )
    db[Account.__name__].update_one(
        {"_id": SYSTEM_ACCOUNT_USER_ID}, {"$set": {"balance": system_account.balance}}
    )
    db[Transaction.__name__].insert_one(to_json(transaction))
    db[Issue.__name__].insert_one(to_json(issue))

    logging.info(f"Created Transaction: {transaction.dict()}")
    logging.info(f"Created Issue: {issue.dict()}")


def replicate_issue_reassign(data: topics.IssueReassignedSchema) -> None:
    logging.info(f"\t >> replicate_issue_reassign({data}")
    db = MongoClient(mongo_url)[DB_NAME]

    issue = Issue(**db[Issue.__name__].find_one({"issue_id": data.issue_id}))

    account = Account(**db[Account.__name__].find_one({"user_id": data.assigned_to}))
    system_account = Account(
        **db[Account.__name__].find_one({"user_id": SYSTEM_ACCOUNT_USER_ID})
    )
    amount = issue.cost_for_assign

    transaction = Transaction(
        account_from=account.user_id,
        account_to=SYSTEM_ACCOUNT_USER_ID,
        description=f"Issue {issue.issue_id} assigned to you",
        created_at=dt.datetime.utcnow(),
        amount=amount,
    )
    account.balance -= amount
    system_account.balance += amount

    db[Account.__name__].update_one(
        {"_id": account.uuid}, {"$set": {"balance": account.balance}}
    )
    db[Account.__name__].update_one(
        {"_id": SYSTEM_ACCOUNT_USER_ID}, {"$set": {"balance": system_account.balance}}
    )
    db[Transaction.__name__].insert_one(to_json(transaction))
    logging.info(f"Created Transaction: {transaction.dict()}")


def replicate_issue_done(data: topics.IssueAssignedSchema) -> None:
    logging.info(f"\t >> replicate_issue_done({data}")
    db = MongoClient(mongo_url)[DB_NAME]

    issue = Issue(**db[Issue.__name__].find_one({"issue_id": data.issue_id}))
    if issue.marked_as_done:
        logging.info(f"Issue {issue.uuid} already marked_as_done, skipping")
        return

    account = Account(**db[Account.__name__].find_one({"user_id": data.assignee_id}))
    system_account = Account(
        **db[Account.__name__].find_one({"user_id": SYSTEM_ACCOUNT_USER_ID})
    )
    amount = issue.cost_for_done

    transaction = Transaction(
        account_from=SYSTEM_ACCOUNT_USER_ID,
        account_to=account.user_id,
        description=f"Issue {issue.issue_id} marked as done",
        created_at=dt.datetime.utcnow(),
        amount=amount,
    )
    account.balance += amount
    system_account.balance -= amount

    # TODO: with atomic commit
    db[Account.__name__].update_one(
        {"_id": account.uuid}, {"$set": {"balance": account.balance}}
    )
    db[Account.__name__].update_one(
        {"_id": SYSTEM_ACCOUNT_USER_ID}, {"$set": {"balance": system_account.balance}}
    )
    db[Transaction.__name__].insert_one(to_json(transaction))
    db[Issue.__name__].update_one(
        {"_id": issue.uuid}, {"$set": {"marked_as_done": True}}
    )

    logging.info(f"Created Transaction: {transaction.dict()}")
    logging.info(f"Marked Issue {issue.uuid} as done")


consumer_config: ty.Dict[topics.Topic, ty.Callable] = {
    topics.USER_CREATED: replicate_account,
    topics.ISSUE_CREATED: replicate_issue_created,
    topics.ISSUE_ASSIGNED: replicate_issue_reassign,
    topics.ISSUE_DONE: replicate_issue_done,
}


if __name__ == "__main__":
    kafka_url = f"{KAFKA_SERVER}:{KAFKA_PORT}"
    topics.start_consumers(consumer_config, kafka_url)

    logging.warning("All threads finished, exiting...")
    sys.exit(99)
