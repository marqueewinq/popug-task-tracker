# Example of manual Mongo migration

import os

from common.connectors import create_db_client
from tasktracker.models import Issue
from tasktracker.utils import split_description_jira_id

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]

client = create_db_client(
    f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
)
db = client[DB_NAME]

for issue_document in db[Issue.__name__].find(
    {"description": {"$regex": r".*\[.*\].*"}}
):
    if "description" not in issue_document:
        continue
    description, jira_id = split_description_jira_id(issue_document["description"])
    db[Issue.__name__].update_one(
        {"_id": issue_document["_id"]},
        {"$set": {"description": description, "jira_id": jira_id}},
    )

client.close()
