import concurrent.futures
import json
import logging
import typing as ty

import kafka

from common import topics


def start_consumer(
    topic: topics.Topic,
    consumer_callback: ty.Callable,
    bootstrap_servers: ty.Union[str, ty.List[str]],
) -> None:
    consumer = kafka.KafkaConsumer(
        topic.name,
        bootstrap_servers=bootstrap_servers,
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


def start_consumers(
    consumer_config: ty.Dict[topics.Topic, ty.Callable],
    bootstrap_servers: ty.Union[str, ty.List[str]],
) -> None:
    if len(consumer_config) == 0:
        return

    if len(consumer_config) == 1:
        for topic, consumer_callback in consumer_config.items():
            start_consumer(topic, consumer_callback, bootstrap_servers)
        return

    logging.info(
        "Threading listeners on topics: "
        + ", ".join([topic.name for topic in consumer_config.keys()])
    )
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(consumer_config)
    ) as executor:
        for topic, consumer_callback in consumer_config.items():
            executor.submit(start_consumer, topic, consumer_callback, bootstrap_servers)
