import logging
import os
import sys
import typing as ty

from common import topics
from fastapi.encoders import jsonable_encoder as to_json
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

    if db[User.__name__].find_one({"user_id": data.user_id}) is not None:
        logging.info("Account already exists")
        return

    user = User(user_id=data.user_id)
    db[User.__name__].insert_one(to_json(user))
    logging.info(f"Created user {data.user_id}")


consumer_config: ty.Dict[topics.Topic, ty.Callable] = {
    topics.USER_CREATED: replicate_user
}


if __name__ == "__main__":
    kafka_url = f"{KAFKA_SERVER}:{KAFKA_PORT}"
    topics.start_consumers(consumer_config, kafka_url)

    logging.warning("All threads finished, exiting...")
    sys.exit(99)
