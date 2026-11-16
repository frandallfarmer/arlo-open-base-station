"""Tiny in-process event bus exposed as Server-Sent Events (GET /events).

Lets Home Assistant / Node-RED / anything react to motion, status and
registration without polling. publish() never blocks: slow subscribers drop
events instead of stalling the camera protocol threads.
"""
import json
import queue
import threading
import time

_subscribers = set()
_lock = threading.Lock()
KEEPALIVE_SECONDS = 15


def publish(event_type, **data):
    data.setdefault("time", time.time())
    payload = (event_type, data)
    with _lock:
        subscribers = list(_subscribers)
    for q in subscribers:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


def sse_stream():
    q = queue.Queue(maxsize=200)
    with _lock:
        _subscribers.add(q)
    try:
        yield ": connected\n\n"
        while True:
            try:
                event_type, data = q.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
    finally:
        with _lock:
            _subscribers.discard(q)
