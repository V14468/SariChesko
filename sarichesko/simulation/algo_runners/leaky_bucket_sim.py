from collections import deque


class LeakyBucketQueue:
    """Fixed-rate output queue — packets drain at a constant rate regardless of input burstiness."""

    def __init__(self, rate_bps: int, burst_bytes: int, packet_size: int = 1500):
        self._rate_pps = rate_bps / (packet_size * 8)  # packets per second
        self._drain_interval = 1.0 / self._rate_pps if self._rate_pps > 0 else 1.0
        self._bucket_size = max(1, burst_bytes // packet_size)
        self._queue: deque = deque()
        self._last_drain = 0.0
        self._drops = 0
        self._departures = 0

    def enqueue(self, packet_id: int, arrival_time: float) -> bool:
        if len(self._queue) >= self._bucket_size:
            self._drops += 1
            return False
        self._queue.append((packet_id, arrival_time))
        return True

    def dequeue(self, current_time: float) -> list[tuple[int, float, float]]:
        departed = []
        while self._queue and current_time >= self._last_drain + self._drain_interval:
            self._last_drain += self._drain_interval
            pid, arrival = self._queue.popleft()
            delay = self._last_drain - arrival
            departed.append((pid, self._last_drain, max(0, delay)))
            self._departures += 1
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