import typing as ty

import fastapi as fa
import random

from common import topics
from tasktracker.models import Issue, IssueStatus


def shuffle_issues(request: fa.Request, user_id_list: ty.List[str]):
    for issue_document in request.app.db[Issue.__name__].find(
        {"status": IssueStatus.todo.value}
    ):
        issue = Issue(**issue_document)

        assigned_from = issue.assignee_id
        assigned_to = random.choice(user_id_list)

        request.app.db[Issue.__name__].update_one(
            {"_id": issue.uuid}, {"$set": {"assignee_id": assigned_to}}
        )

        request.app.kafka_producer.send(
            topics.TASK_ASSIGNED,
            {"assigned_from": assigned_from, "assigned_to": assigned_to},
        )
