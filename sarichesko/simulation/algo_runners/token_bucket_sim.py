from collections import deque


class TokenBucketQueue:
    """Token-replenishing queue — allows controlled bursts up to the token capacity."""

    def __init__(self, rate_bps: int, burst_bytes: int, latency_ms: int = 50, packet_size: int = 1500):
        self._rate_pps = rate_bps / (packet_size * 8)
        self._max_tokens = max(1, burst_bytes // packet_size)
        self._tokens = float(self._max_tokens)
        self._max_queue = max(self._max_tokens * 2, int(self._rate_pps * (latency_ms / 1000.0)))
        self._queue: deque = deque()
        self._last_refill = 0.0
        self._drops = 0
        self._departures = 0

    def enqueue(self, packet_id: int, arrival_time: float) -> bool:
        if len(self._queue) >= self._max_queue:
            self._drops += 1
            return False
        self._queue.append((packet_id, arrival_time))
        return True

    def dequeue(self, current_time: float) -> list[tuple[int, float, float]]:
        # Refill tokens
        elapsed = current_time - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate_pps)
        self._last_refill = current_time

        departed = []
        while self._queue and self._tokens >= 1.0:
            self._tokens -= 1.0
            pid, arrival = self._queue.popleft()
            delay = current_time - arrival
            departed.append((pid, current_time, max(0, delay)))
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