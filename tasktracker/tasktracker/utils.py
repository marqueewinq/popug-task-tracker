import typing as ty

import fastapi as fa
import random

from tasktracker.models import Issue, IssueStatus


def shuffle_issues(request: fa.Request, user_id_list: ty.List[str]):
    for issue_document in request.app.db[Issue.__name__].find(
        {"status": IssueStatus.todo.value}
    ):
        assignee_id = random.choice(user_id_list)
        request.app.db[Issue.__name__].update_one(
            {"_id": issue_document["_id"]}, {"$set": {"assignee_id": assignee_id}}
        )
