import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watering_safety import WateringGuard  # noqa: E402

T0 = 1_760_000_000.0  # fixed epoch


def g(tmp_path, **lim):
    guard = WateringGuard.load(tmp_path / "s.json")
    guard.update_limits(lim)
    return guard


def test_daily_pulse_cap(tmp_path):
    w = g(tmp_path, maxPulsesPerDay=2, minPulseIntervalSec=0)
    for i in range(2):
        assert w.check(1000, "auto", T0 + i)[0]
        w.record_pulse(1000, "auto", 30, T0 + i)
    ok, why = w.check(1000, "auto", T0 + 5)
    assert not ok and "pulse cap" in why


def test_daily_ms_cap(tmp_path):
    w = g(tmp_path, maxPumpMsPerDay=1500, minPulseIntervalSec=0)
    w.record_pulse(1000, "home", 30, T0)
    assert not w.check(1000, "home", T0 + 1)[0]


def test_cap_resets_next_day(tmp_path):
    w = g(tmp_path, maxPulsesPerDay=1, minPulseIntervalSec=0)
    w.record_pulse(1000, "auto", 30, T0)
    assert not w.check(1000, "auto", T0 + 10)[0]
    assert w.check(1000, "auto", T0 + 86400)[0]


def test_min_interval_only_auto(tmp_path):
    w = g(tmp_path, minPulseIntervalSec=1800)
    w.record_pulse(1000, "auto", 30, T0)
    assert not w.check(1000, "auto", T0 + 300)[0]
    assert w.check(1000, "home", T0 + 300)[0]
    assert w.check(1000, "auto", T0 + 1801)[0]


def test_open_circuit_locks(tmp_path):
    w = g(tmp_path)
    assert w.observe_reading(1023, 0, 600, T0)
    assert not w.check(1000, "home", T0 + 1)[0]


def test_probe_in_air_locks(tmp_path):
    w = g(tmp_path)
    assert w.observe_reading(700, 0, 600, T0)


def test_sudden_dry_jump_locks(tmp_path):
    w = g(tmp_path)
    assert w.observe_reading(350, 70, 600, T0) is None
    assert "jumped" in w.observe_reading(590, 3, 600, T0 + 5)


def test_normal_drift_ok(tmp_path):
    w = g(tmp_path)
    for i in range(10):
        assert w.observe_reading(350 + i * 5, 60, 600, T0 + i * 60) is None


def test_no_response_locks(tmp_path):
    w = g(tmp_path, noResponsePulses=2, minPulseIntervalSec=0)
    for i in range(2):
        w.record_pulse(1000, "auto", 20, T0 + i * 100)
        w.observe_reading(500, 20, 600, T0 + i * 100 + 10)
    assert w.lockout and "no moisture rise" in w.lockout


def test_lockout_persists_and_resets(tmp_path):
    w = g(tmp_path)
    w.trip("test", T0)
    w2 = WateringGuard.load(tmp_path / "s.json")
    assert w2.lockout == "test"
    w2.reset()
    assert WateringGuard.load(tmp_path / "s.json").lockout is None
