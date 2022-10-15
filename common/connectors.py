import json
import logging
import typing as ty
from time import sleep

import kafka
import pymongo


def create_kafka_producer(
    bootstrap_servers: ty.Union[str, ty.List[str]]
) -> kafka.KafkaProducer:
    for delay in range(10):
        try:
            return kafka.KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                linger_ms=100,
            )
        except kafka.errors.NoBrokersAvailable:
            logging.info(f"No brokers available, retrying in {delay} seconds")
            sleep(delay)
    raise RuntimeError("Couldn't connect to Kafka")


def create_db_client(mongo_url: str) -> pymongo.MongoClient:
    return pymongo.MongoClient(mongo_url)
