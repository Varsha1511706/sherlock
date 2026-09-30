# src/stream.py
"""Simulated streaming ingester for rolling-window analysis."""
import time
from collections import deque


class RollingLogStream:
    def __init__(self, logs: list, window: int = 5000):
        self.logs = logs
        self.window = window
        self.buf = deque(maxlen=window)
        self.idx = 0

    def tick(self, n: int = 10) -> list:
        batch = self.logs[self.idx:self.idx + n]
        self.idx = (self.idx + n) % max(len(self.logs), 1)
        self.buf.extend(batch)
        return list(self.buf)
