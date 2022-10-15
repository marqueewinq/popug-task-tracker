import typing as ty

import fastapi as fa
import random
import re


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

        topics.send_to_topic(
            request.app.kafka_producer,
            topics.ISSUE_ASSIGNED,
            topics.IssueReassignedSchema(
                assigned_from=assigned_from, assigned_to=assigned_to
            ),
        )


def split_description_jira_id(description: str) -> ty.Tuple[str, str]:
    result = re.findall(r"\[.*?\]", description)
    if len(result) != 1:
        return description, ""
    jira_id = result[0]
    return description.replace(jira_id, ""), jira_id
