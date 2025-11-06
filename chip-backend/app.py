import json
import logging
import os
import time
from collections import Counter
from threading import Event, Lock, Thread
from typing import Dict, List, Optional, Union

from flask import Flask, jsonify, request

try:
    from kafka import KafkaConsumer, KafkaProducer  # type: ignore
except ImportError:  # pragma: no cover - kafka-python not installed yet
    KafkaConsumer = KafkaProducer = None


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

app = Flask(__name__)


class KafkaScoreTracker:
    """Tracks chip totals by consuming the shared Kafka topic."""

    def __init__(self):
        self.brokers = [b.strip() for b in os.getenv("KAFKA_BROKERS", "").split(",") if b.strip()]
        self.topic = os.getenv("KAFKA_TOPIC", "chip-moves")
        self.group_id = os.getenv("KAFKA_GROUP_ID", "chip-backend")
        self.auto_offset_reset = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")
        self._scores = Counter()
        self._lock = Lock()
        self._stop = Event()
        self._consumer_thread = None  # type: Optional[Thread]
        self._producer = None  # lazy-initialized KafkaProducer
        self._consumer_ready = False

        if self._is_enabled():
            self._start_io()
        elif not self.brokers:
            log.info("Kafka integration disabled: KAFKA_BROKERS not set")
        else:
            log.warning("Kafka libraries missing; run pip install -r requirements.txt")

    def _is_enabled(self) -> bool:
        return bool(self.brokers) and KafkaProducer is not None and KafkaConsumer is not None

    def _start_io(self) -> None:
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=self.brokers,
                value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
                linger_ms=10,
            )
            log.info("Kafka producer initialized for %s", ",".join(self.brokers))
        except Exception as exc:  # pragma: no cover - relies on Kafka runtime
            log.error("Failed to create Kafka producer: %s", exc)
            self._producer = None

        self._consumer_thread = Thread(target=self._consume_loop, name="kafka-consumer", daemon=True)
        self._consumer_thread.start()

    def _consume_loop(self) -> None:  # pragma: no cover - requires Kafka runtime
        if KafkaConsumer is None:
            return

        while not self._stop.is_set():
            try:
                consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.brokers,
                    group_id=self.group_id,
                    enable_auto_commit=True,
                    auto_offset_reset=self.auto_offset_reset,
                    value_deserializer=lambda data: json.loads(data.decode("utf-8")),
                )
                self._consumer_ready = True
                log.info("Kafka consumer listening on topic '%s'", self.topic)
                for message in consumer:
                    if self._stop.is_set():
                        break
                    payload = message.value or {}
                    player = payload.get("player") or "Unknown"
                    chips = int(payload.get("chips", 0))
                    if chips:
                        self._apply_score(player, chips)
                consumer.close()
            except Exception as exc:
                self._consumer_ready = False
                log.warning("Kafka consumer error: %s", exc)
                time.sleep(5)

    def publish_move(self, player: str, chips: int) -> bool:
        payload = {"player": player, "chips": chips, "source": "chip-backend"}
        if not self._producer:
            log.debug("No Kafka producer available; recording move locally")
            self._apply_score(player, chips)
            return False

        try:
            self._producer.send(self.topic, payload).get(timeout=5)
            log.debug("Published move for %s (%s chips)", player, chips)
            return True
        except Exception as exc:  # pragma: no cover - requires Kafka runtime
            log.error("Failed to publish Kafka message: %s", exc)
            self._apply_score(player, chips)
            return False

    def _apply_score(self, player: str, chips: int) -> None:
        with self._lock:
            self._scores[player] += chips

    def leaderboard(self, limit: int = 10) -> List[Dict[str, Union[int, str]]]:
        with self._lock:
            if not self._scores:
                return []
            top = self._scores.most_common(limit)
        return [{"player": player, "chips": chips} for player, chips in top]


kafka_tracker = KafkaScoreTracker()


@app.get("/healthz")
def healthz():
    kafka_status = "ok" if kafka_tracker._consumer_ready or not kafka_tracker.brokers else "degraded"
    return jsonify({"status": "ok", "kafka": kafka_status}), 200


@app.get("/livez")
def livez():
    return "alive", 200


@app.post("/api/collect")
def collect():
    data = request.json or {}
    player = data.get("player", "You")
    chips = int(data.get("chips", 1))
    kafka_tracker.publish_move(player, chips)
    return jsonify({"message": f"{player} collected {chips} chips!"})


@app.get("/api/leaderboard")
def leaderboard():
    scores = kafka_tracker.leaderboard()
    if not scores:
        scores = [
            {"player": "Alice", "chips": 10},
            {"player": "Bob", "chips": 7},
            {"player": "Charlie", "chips": 5},
        ]
    return jsonify(scores)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
