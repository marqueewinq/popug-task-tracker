import kafka
import json
from common import topics
from pydantic import BaseModel


class KafkaTopicValidationError(Exception):
    pass


def send_to_topic(
    producer: kafka.KafkaProducer, topic: topics.Topic, message: BaseModel
) -> None:
    assert isinstance(
        message, topic.base_model
    ), f"{type(message)=}, but topic accepts {topic.base_model}"
    producer.send(topic.name, json.loads(message.json()))
