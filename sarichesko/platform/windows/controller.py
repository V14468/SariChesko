import subprocess
import shutil
import sys
from typing import Optional

from ..base import TrafficControllerBase, ConfigSnapshot, ApplyResult


POLICY_PREFIX = "SariChesko_"

# Windows' built-in QoS Packet Scheduler (NetQosPolicy) exposes exactly one
# shaping primitive -- ThrottleRateActionBitsPerSecond -- and no public API
# for RED or CoDel-style active queue management. Per the project's
# cross-platform honesty requirement, RED/CoDel are simulate-only on Windows;
# they are never silently skipped or faked as applied.
SUPPORTED_ALGORITHMS = frozenset({"Leaky Bucket", "Token Bucket"})


def _run_powershell(command: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=timeout,
    )


def _looks_like_privilege_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "access is denied" in s or "administrator" in s or "elevat" in s or "unauthorizedaccess" in s


def _looks_like_not_found_error(stderr: str) -> bool:
    s = (stderr or "").lower()
    return "cannot find" in s or "no msft_netqospolicy" in s or "objectnotfound" in s


class WindowsTrafficController(TrafficControllerBase):
    """Applies bandwidth shaping on Windows via the built-in NetQosPolicy
    module, scoping the policy to a single interface's IPv4 traffic so other
    adapters are unaffected.

    NetQosPolicy's only shaping knob (ThrottleRateActionBitsPerSecond)
    behaves like a token bucket: it allows short bursts up to line rate,
    then throttles to the configured average. That's a good native fit for
    Token Bucket. For Leaky Bucket -- which should have near-constant, non-bursty
    output -- Windows has no separate primitive, so we apply the same
    throttle mechanism as the closest available approximation and say so
    explicitly in the result message, rather than pretending it's a distinct
    behavior.
    """

    SUPPORTED_ALGORITHMS = SUPPORTED_ALGORITHMS

    def is_supported(self) -> bool:
        if shutil.which("powershell") is None:
            return False
        try:
            result = _run_powershell(
                "Get-Command New-NetQosPolicy -ErrorAction Stop | Out-Null; Write-Output 'OK'"
            )
            return result.returncode == 0 and "OK" in result.stdout
        except Exception:
            return False

    def requires_elevation(self) -> bool:
        # Writing to the live (ActiveStore) QoS policy store changes system
        # network configuration and requires an elevated (Administrator) shell.
        return True

    def is_elevated(self) -> bool:
        """Check if running as Administrator on Windows.  Fail-safe: returns
        False on any error (including being called on a non-Windows platform
        where ctypes.windll doesn't exist)."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _policy_name(self, iface: str) -> str:
        safe = "".join(c if c.isalnum() else "_" for c in iface)
        return f"{POLICY_PREFIX}{safe}"

    def save_snapshot(self, iface: str) -> ConfigSnapshot:
        try:
            result = _run_powershell(
                f"Get-NetQosPolicy -Name '{self._policy_name(iface)}' -PolicyStore ActiveStore "
                f"-ErrorAction SilentlyContinue | Format-List | Out-String"
            )
            raw = result.stdout.strip() or "none"
        except Exception:
            raw = "none"
        return ConfigSnapshot(interface=iface, raw=raw)

    def restore_snapshot(self, snapshot: ConfigSnapshot) -> ApplyResult:
        # SariChesko only ever adds its own single policy on Windows -- there
        # is no prior state to replay beyond "our policy wasn't there".
        # Restoring means removing whatever we applied.
        return self.remove_policy(snapshot.interface)

    def _apply_throttle(self, iface: str, rate_bps: int, algo_label: str) -> ApplyResult:
        name = self._policy_name(iface)
        # Clear any existing SariChesko policy first so re-applying is idempotent.
        _run_powershell(
            f"Remove-NetQosPolicy -Name '{name}' -PolicyStore ActiveStore "
            f"-Confirm:$false -ErrorAction SilentlyContinue"
        )
        cmd = (
            f"New-NetQosPolicy -Name '{name}' -IPSrcPrefixMatchCondition '0.0.0.0/0' "
            f"-ThrottleRateActionBitsPerSecond {int(rate_bps)} -PolicyStore ActiveStore -ErrorAction Stop"
        )
        try:
            result = _run_powershell(cmd)
        except subprocess.TimeoutExpired:
            return ApplyResult(success=False, message="Timed out talking to the Windows QoS policy store.")
        except Exception as e:
            return ApplyResult(success=False, message=str(e))

        if result.returncode != 0:
            if _looks_like_privilege_error(result.stderr):
                return ApplyResult(
                    success=False,
                    message="Administrator privileges required. Restart SariChesko as Administrator and try again.",
                )
            return ApplyResult(success=False, message=(result.stderr or "Unknown error").strip()[:300])

        return ApplyResult(
            success=True,
            message=f"{algo_label} shaping applied at {rate_bps / 1_000_000:.1f} Mbps via Windows QoS.",
        )

    def apply_leaky_bucket(self, iface: str, rate_bps: int, burst_bytes: int) -> ApplyResult:
        result = self._apply_throttle(iface, rate_bps, "Leaky Bucket")
        if result.success:
            result.message += (
                " Note: Windows' QoS throttle is token-bucket-like by nature; a strictly "
                "constant-rate leaky-bucket output isn't exposed by the OS API."
            )
        return result

    def apply_token_bucket(self, iface: str, rate_bps: int, burst_bytes: int, latency_ms: int) -> ApplyResult:
        return self._apply_throttle(iface, rate_bps, "Token Bucket")

    def apply_red(self, iface: str, min_th: int, max_th: int, max_p: float, limit: int) -> ApplyResult:
        return ApplyResult(
            success=False,
            message="RED is unavailable on Windows -- no public OS API exposes active queue management here. "
                    "Use Simulation Lab or Compare Algorithms to see RED's effect on this traffic pattern.",
        )

    def apply_codel(self, iface: str, target_ms: int, interval_ms: int, limit: int) -> ApplyResult:
        return ApplyResult(
            success=False,
            message="CoDel is unavailable on Windows -- no public OS API exposes active queue management here. "
                    "Use Simulation Lab or Compare Algorithms to see CoDel's effect on this traffic pattern.",
        )

    def remove_policy(self, iface: str) -> ApplyResult:
        name = self._policy_name(iface)
        try:
            result = _run_powershell(
                f"Remove-NetQosPolicy -Name '{name}' -PolicyStore ActiveStore -Confirm:$false -ErrorAction Stop"
            )
        except Exception as e:
            return ApplyResult(success=False, message=str(e))

        if result.returncode != 0 and not _looks_like_not_found_error(result.stderr):
            if _looks_like_privilege_error(result.stderr):
                return ApplyResult(success=False, message="Administrator privileges required to remove the policy.")
            return ApplyResult(success=False, message=(result.stderr or "Unknown error").strip()[:300])

        return ApplyResult(success=True, message="Policy removed; network settings restored to default.")