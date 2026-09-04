import random
from collections import deque


class REDQueue:
    """Random Early Detection — probabilistically drops packets as average queue grows."""

    def __init__(self, min_th: int, max_th: int, max_p: float, limit: int, w_q: float = 0.002):
        self._min_th = min_th
        self._max_th = max_th
        self._max_p = max_p
        self._limit = limit
        self._w_q = w_q

        self._queue: deque = deque()
        self._avg_queue = 0.0
        self._count = 0
        self._drops = 0
        self._departures = 0

    def enqueue(self, packet_id: int, arrival_time: float) -> bool:
        # Update EWMA of queue size
        self._avg_queue = (1 - self._w_q) * self._avg_queue + self._w_q * len(self._queue)

        if self._avg_queue < self._min_th:
            # Accept
            self._count = -1
        elif self._avg_queue < self._max_th:
            # Probabilistic drop
            self._count += 1
            pb = self._max_p * (self._avg_queue - self._min_th) / (self._max_th - self._min_th)
            pa = pb / (1 - self._count * pb) if (1 - self._count * pb) > 0 else 1.0
            if random.random() < pa:
                self._drops += 1
                self._count = 0
                return False
        else:
            # Forced drop
            self._drops += 1
            self._count = 0
            return False

        if len(self._queue) >= self._limit:
            self._drops += 1
            return False

        self._queue.append((packet_id, arrival_time))
        return True

    def dequeue(self, current_time: float, count: int = 1) -> list[tuple[int, float, float]]:
        departed = []
        for _ in range(count):
            if not self._queue:
                break
            pid, arrival = self._queue.popleft()
            delay = current_time - arrival
            departed.append((pid, current_time, max(0, delay)))
            self._departures += 1
        return departed

    @property
    def depth(self) -> int:
        return len(self._queue)

    @property
    def avg_depth(self) -> float:
        return self._avg_queue

    @property
    def drops(self) -> int:
        return self._drops

    @property
    def departures(self) -> int:
        return self._departures