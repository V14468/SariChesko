from collections import deque


class CoDelQueue:
    """Controlled Delay — drops packets when sojourn time exceeds target persistently."""

    def __init__(self, target_ms: float = 5.0, interval_ms: float = 100.0, limit: int = 1024):
        self._target_s = target_ms / 1000.0
        self._interval_s = interval_ms / 1000.0
        self._limit = limit

        self._queue: deque = deque()
        self._dropping = False
        self._first_above_time = 0.0
        self._drop_next = 0.0
        self._drop_count = 0
        self._drops = 0
        self._departures = 0

    def enqueue(self, packet_id: int, arrival_time: float) -> bool:
        if len(self._queue) >= self._limit:
            self._drops += 1
            return False
        self._queue.append((packet_id, arrival_time))
        return True

    def dequeue(self, current_time: float) -> list[tuple[int, float, float]]:
        if not self._queue:
            return []

        pid, arrival = self._queue.popleft()
        sojourn = current_time - arrival
        departed = [(pid, current_time, max(0, sojourn))]
        self._departures += 1

        if sojourn < self._target_s:
            self._first_above_time = 0.0
        else:
            if self._first_above_time == 0.0:
                self._first_above_time = current_time + self._interval_s
            elif current_time >= self._first_above_time:
                # Drop from head
                if self._queue:
                    drop_pid, drop_arrival = self._queue.popleft()
                    self._drops += 1
                    self._drop_count += 1
                    self._first_above_time = current_time + self._interval_s / (self._drop_count ** 0.5)

        return departed

    @property
    def depth(self) -> int:
        return len(self._queue)

    @property
    def drops(self) -> int:
        return self._drops

    @property
    def departures(self) -> int:
        return self._departures