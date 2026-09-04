import random
import math
from .engine_base import (
    SimulationEngineBase, SimConfig, SimulationResult, SimMetrics,
    PacketEvent, AlgorithmType,
)
from .algo_runners.leaky_bucket_sim import LeakyBucketQueue
from .algo_runners.token_bucket_sim import TokenBucketQueue
from .algo_runners.red_sim import REDQueue
from .algo_runners.codel_sim import CoDelQueue


class PythonSimulationEngine(SimulationEngineBase):
    """Discrete-event simulation engine — pure Python, no external dependencies."""

    def run(self, config: SimConfig) -> SimulationResult:
        dt = 0.001  # 1ms time steps
        steps = int(config.duration_s / dt)
        link_pps = (config.link_bandwidth_mbps * 1_000_000) / (1500 * 8)
        service_per_step = max(1, int(link_pps * dt))

        # Create the queue/algorithm
        queue = self._create_queue(config)

        events = []
        queue_depths = []
        latencies = []
        packet_id = 0
        total_arrived = 0

        for step in range(steps):
            t = step * dt

            # Generate arrivals based on scenario
            arrivals = self._generate_arrivals(config, t, dt, link_pps)

            for _ in range(arrivals):
                packet_id += 1
                total_arrived += 1
                accepted = queue.enqueue(packet_id, t)

                if len(events) < 5000:
                    events.append(PacketEvent(
                        time=t, event="arrive" if accepted else "drop",
                        packet_id=packet_id, queue_depth=queue.depth, delay_ms=0,
                    ))

            # Service/dequeue
            if isinstance(queue, (LeakyBucketQueue, TokenBucketQueue)):
                departed = queue.dequeue(t)
            elif isinstance(queue, REDQueue):
                departed = queue.dequeue(t, count=service_per_step)
            elif isinstance(queue, CoDelQueue):
                departed = []
                for _ in range(service_per_step):
                    d = queue.dequeue(t)
                    if d:
                        departed.extend(d)
                    else:
                        break
            else:
                departed = []

            for pid, dep_time, delay in departed:
                delay_ms = delay * 1000 + config.link_delay_ms
                latencies.append((t, delay_ms))
                if len(events) < 5000:
                    events.append(PacketEvent(
                        time=dep_time, event="depart",
                        packet_id=pid, queue_depth=queue.depth, delay_ms=delay_ms,
                    ))

            # Sample queue depth every 10ms
            if step % 10 == 0:
                queue_depths.append((t, queue.depth))

        # Compute metrics
        dropped = queue.drops
        delivered = queue.departures
        all_latencies = [lat for _, lat in latencies]

        metrics = SimMetrics(
            throughput_mbps=(delivered * 1500 * 8) / (config.duration_s * 1_000_000) if config.duration_s > 0 else 0,
            avg_latency_ms=sum(all_latencies) / len(all_latencies) if all_latencies else 0,
            max_latency_ms=max(all_latencies) if all_latencies else 0,
            loss_pct=(dropped / total_arrived * 100) if total_arrived > 0 else 0,
            avg_queue_depth=sum(d for _, d in queue_depths) / len(queue_depths) if queue_depths else 0,
            max_queue_depth=max(d for _, d in queue_depths) if queue_depths else 0,
            fairness_index=self._estimate_fairness(config.num_flows, delivered),
            total_packets=total_arrived,
            dropped_packets=dropped,
            delivered_packets=delivered,
        )

        return SimulationResult(
            scenario=config.scenario,
            algorithm=config.algorithm.value,
            config=config,
            duration_s=config.duration_s,
            metrics=metrics,
            events=events,
            queue_depth_over_time=queue_depths,
            latency_over_time=latencies,
            engine_used="python_fallback",
        )

    def _create_queue(self, config: SimConfig):
        if config.algorithm == AlgorithmType.LEAKY_BUCKET:
            return LeakyBucketQueue(config.rate_bps, config.burst_bytes)
        elif config.algorithm == AlgorithmType.TOKEN_BUCKET:
            return TokenBucketQueue(config.rate_bps, config.burst_bytes, config.latency_ms)
        elif config.algorithm == AlgorithmType.RED:
            return REDQueue(config.red_min_th, config.red_max_th, config.red_max_p, config.queue_size)
        elif config.algorithm == AlgorithmType.CODEL:
            return CoDelQueue(config.codel_target_ms, config.codel_interval_ms, config.queue_size)
        else:
            return CoDelQueue(5, 100, config.queue_size)

    def _generate_arrivals(self, config: SimConfig, t: float, dt: float, link_pps: float) -> int:
        load_factor = 1.2  # slightly over capacity to create congestion

        if config.scenario == "bulk_transfer":
            rate = link_pps * load_factor * dt
            return max(0, int(random.expovariate(1.0 / rate))) if rate > 0 else 0

        elif config.scenario == "bursty_traffic":
            burst_period = 0.5
            phase = (t % burst_period) / burst_period
            if phase < 0.3:
                rate = link_pps * load_factor * 2.5 * dt
            else:
                rate = link_pps * 0.2 * dt
            return max(0, int(random.expovariate(1.0 / rate))) if rate > 0 else 0

        elif config.scenario == "mixed_traffic":
            base = link_pps * 0.5 * dt
            burst = link_pps * 1.5 * dt if random.random() < 0.1 else 0
            rate = base + burst
            return max(0, int(random.expovariate(1.0 / rate))) if rate > 0 else 0

        else:
            rate = link_pps * load_factor * dt
            return max(0, int(random.expovariate(1.0 / rate))) if rate > 0 else 0

    def _estimate_fairness(self, num_flows: int, total_delivered: int) -> float:
        if num_flows <= 1:
            return 1.0
        per_flow = total_delivered / num_flows
        shares = [per_flow * (0.8 + random.random() * 0.4) for _ in range(num_flows)]
        sum_x = sum(shares)
        sum_x2 = sum(x * x for x in shares)
        if sum_x2 == 0:
            return 1.0
        return (sum_x ** 2) / (num_flows * sum_x2)