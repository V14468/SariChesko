import subprocess
import shutil

from ..base import TrafficControllerBase, ConfigSnapshot, ApplyResult


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _looks_like_privilege_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "operation not permitted" in s or "permission denied" in s


def _looks_like_not_found_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "no such file" in s or "cannot find device" in s or "cannot delete" in s


class LinuxTrafficController(TrafficControllerBase):
    """Applies queue management on Linux via `tc` (iproute2), replacing the
    root qdisc on the target interface. All four algorithms map to native
    Linux qdiscs:

      Leaky Bucket -> tbf with a minimal burst (forces near-constant output)
      Token Bucket -> tbf with a real burst allowance (native token bucket)
      RED          -> red
      CoDel        -> codel (native, most direct 1:1 mapping of the four)

    Linux's `tc tbf` qdisc IS a Token Bucket Filter -- the kernel has no
    separate "leaky bucket" qdisc. Setting `burst` to roughly one MTU forces
    the bucket to release packets at close to a fixed rate, which is the
    standard, documented way to approximate leaky-bucket behavior with tc.
    """

    SUPPORTED_ALGORITHMS = frozenset({"Leaky Bucket", "Token Bucket", "RED", "CoDel"})

    def is_algorithm_supported(self, algorithm: str) -> bool:
        return algorithm in self.SUPPORTED_ALGORITHMS

    def is_supported(self) -> bool:
        return shutil.which("tc") is not None

    def requires_elevation(self) -> bool:
        # Modifying qdiscs requires CAP_NET_ADMIN, i.e. root.
        return True

    def save_snapshot(self, iface: str) -> ConfigSnapshot:
        try:
            result = _run(["tc", "qdisc", "show", "dev", iface])
            raw = result.stdout.strip() or "none"
        except Exception:
            raw = "none"
        return ConfigSnapshot(interface=iface, raw=raw)

    def restore_snapshot(self, snapshot: ConfigSnapshot) -> ApplyResult:
        # We only ever replace the root qdisc, so "restore" removes ours and
        # lets the kernel fall back to its configured default (pfifo_fast /
        # fq_codel depending on distro). Reliably re-creating an arbitrary
        # prior qdisc hierarchy from `tc qdisc show` text isn't possible in
        # general, so this is explicit about what actually happens rather
        # than pretending it's a full state replay.
        return self.remove_policy(snapshot.interface)

    def _replace_root_qdisc(self, iface: str, qdisc_args: list[str], success_message: str) -> ApplyResult:
        _run(["tc", "qdisc", "del", "dev", iface, "root"])  # clear any existing root qdisc; ignore errors here

        try:
            result = _run(["tc", "qdisc", "add", "dev", iface, "root"] + qdisc_args)
        except subprocess.TimeoutExpired:
            return ApplyResult(success=False, message="Timed out talking to the kernel traffic control subsystem.")
        except FileNotFoundError:
            return ApplyResult(success=False, message="'tc' (iproute2) is not installed on this system.")
        except Exception as e:
            return ApplyResult(success=False, message=str(e))

        if result.returncode != 0:
            if _looks_like_privilege_error(result.stderr):
                return ApplyResult(success=False, message="Root privileges required. Re-run SariChesko with sudo and try again.")
            return ApplyResult(success=False, message=(result.stderr or "Unknown tc error").strip()[:300])

        return ApplyResult(success=True, message=success_message)

    def apply_leaky_bucket(self, iface: str, rate_bps: int, burst_bytes: int) -> ApplyResult:
        rate_kbit = max(1, int(rate_bps / 1000))
        min_burst = 1600  # ~ one MTU; keeps the bucket effectively always-draining at a fixed rate
        args = ["tbf", "rate", f"{rate_kbit}kbit", "burst", f"{min_burst}b", "latency", "50ms"]
        return self._replace_root_qdisc(
            iface, args,
            f"Leaky Bucket applied at {rate_kbit / 1000:.2f} Mbps (tbf, minimal burst for near-constant output)."
        )

    def apply_token_bucket(self, iface: str, rate_bps: int, burst_bytes: int, latency_ms: int) -> ApplyResult:
        rate_kbit = max(1, int(rate_bps / 1000))
        burst = max(1600, int(burst_bytes))
        args = ["tbf", "rate", f"{rate_kbit}kbit", "burst", f"{burst}b", "latency", f"{latency_ms}ms"]
        return self._replace_root_qdisc(
            iface, args,
            f"Token Bucket applied at {rate_kbit / 1000:.2f} Mbps with a {burst}B burst allowance (tbf)."
        )

    def apply_red(self, iface: str, min_th: int, max_th: int, max_p: float, limit: int) -> ApplyResult:
        # min_th/max_th/limit arrive from the recommendation engine as small
        # abstract thresholds tuned for the simulation model, not real byte
        # sizes. We scale them into a plausible byte-scale buffer (x1000) so
        # tc gets sane real-world values for a typical residential link.
        # True bandwidth-delay-product-based sizing is noted as future work.
        avpkt = 1000
        min_bytes = max(avpkt, int(min_th) * 1000)
        max_bytes = max(min_bytes + avpkt, int(max_th) * 1000)
        limit_bytes = max(max_bytes + avpkt, int(limit) * 1000)
        burst = max(1, int((min_bytes + min_bytes + max_bytes) / (3 * avpkt)))
        args = [
            "red", "limit", str(limit_bytes), "min", str(min_bytes), "max", str(max_bytes),
            "avpkt", str(avpkt), "burst", str(burst), "probability", f"{max_p}",
        ]
        return self._replace_root_qdisc(
            iface, args,
            f"RED applied (min={min_bytes}B, max={max_bytes}B, drop probability {max_p})."
        )

    def apply_codel(self, iface: str, target_ms: int, interval_ms: int, limit: int) -> ApplyResult:
        args = ["codel", "target", f"{target_ms}ms", "interval", f"{interval_ms}ms", "limit", str(limit)]
        return self._replace_root_qdisc(
            iface, args,
            f"CoDel applied (target={target_ms}ms, interval={interval_ms}ms, limit={limit} packets)."
        )

    def remove_policy(self, iface: str) -> ApplyResult:
        try:
            result = _run(["tc", "qdisc", "del", "dev", iface, "root"])
        except Exception as e:
            return ApplyResult(success=False, message=str(e))

        if result.returncode != 0 and not _looks_like_not_found_error(result.stderr):
            if _looks_like_privilege_error(result.stderr):
                return ApplyResult(success=False, message="Root privileges required to remove the qdisc.")
            return ApplyResult(success=False, message=(result.stderr or "Unknown tc error").strip()[:300])

        return ApplyResult(success=True, message="Qdisc removed; interface restored to the kernel default.")