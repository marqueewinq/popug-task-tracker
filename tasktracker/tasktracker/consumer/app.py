import concurrent.futures
import json
import os
import sys
import typing as ty
import logging

from common import topics
from fastapi.encoders import jsonable_encoder as to_json
import kafka
from pymongo import MongoClient
from tasktracker.models import User


DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]

KAFKA_PORT = os.environ["KAFKA_PORT"]
KAFKA_SERVER = os.environ["KAFKA_SERVER"]

mongo_url = (
    f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
)

logging.basicConfig(level=logging.INFO)


def replicate_user(data: topics.UserCreatedSchema) -> None:
    db = MongoClient(mongo_url)[DB_NAME]
    user = User(user_id=data.user_id)
    inserted_user = db[User.__name__].insert_one(to_json(user))
    logging.info(f"Created user {inserted_user.inserted_id}")


def start_consumer(topic: topics.Topic, consumer_callback: ty.Callable) -> None:
    consumer = kafka.KafkaConsumer(
        topic.name,
        bootstrap_servers=f"{KAFKA_SERVER}:{KAFKA_PORT}",
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        enable_auto_commit=True,
    )
    logging.info(f"Started listening on {topic.name}")

    for message in consumer:
        logging.info(
            "Received: %s:%d:%d: key=%s value=%s"
            % (
                message.topic,
                message.partition,
                message.offset,
                message.key,
                message.value,
            )
        )
        validated_data = topic.base_model(**message.value)
        try:
            consumer_callback(validated_data)
        except Exception as e:
            logging.exception(e)
            raise


consumer_config: ty.Dict[str, ty.Callable] = {topics.USER_CREATED: replicate_user}


def main():
    logging.info(
        "Threding listeners on topics: "
        + ", ".join([topic.name for topic in consumer_config.keys()])
    )
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(consumer_config)
    ) as executor:
        for topic, consumer_callback in consumer_config.items():
            executor.submit(start_consumer, topic, consumer_callback)

    # start_consumer(topics.USER_CREATED, replicate_user)


if __name__ == "__main__":
    main()

    sys.exit(99)
