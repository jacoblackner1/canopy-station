import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watering_safety import WateringGuard, parse_sensors  # noqa: E402

T0 = 1_760_000_000.0


def g(tmp_path, **lim):
    w = WateringGuard.load(tmp_path / "s.json")
    w.update_limits(lim)
    return w


def test_parse_sensors():
    assert parse_sensors("MOISTURE:400|LIGHT:300|PUMP:0|FAULT:0|LEAK:1|LOW:-") == {"leak": True, "low": None}
    assert parse_sensors("MOISTURE:400|LIGHT:300|PUMP:0|FAULT:0") == {"leak": None, "low": None}
    assert parse_sensors("FAULT:0|LEAK:0|LOW:1") == {"leak": False, "low": True}


def test_disabled_by_default_ignores_sensors(tmp_path):
    w = g(tmp_path)
    assert w.observe_sensors(True, True, T0) is None
    assert w.lockout is None and w.check(1000, "home", T0)[0]


def test_leak_latches_lockout(tmp_path):
    w = g(tmp_path, leakSensorEnabled=True)
    w.observe_sensors(True, None, T0)
    assert "leak" in w.lockout
    w.observe_sensors(False, None, T0 + 5)  # drying doesn't auto-clear
    assert not w.check(1000, "home", T0 + 6)[0]
    w.reset()
    assert w.check(1000, "home", T0 + 7)[0]


def test_low_water_blocks_until_refilled(tmp_path):
    w = g(tmp_path, lowWaterSensorEnabled=True)
    w.observe_sensors(None, True, T0)
    ok, why = w.check(1000, "home", T0)
    assert not ok and "reservoir low" in why
    w.observe_sensors(None, False, T0 + 1)
    assert w.check(1000, "home", T0 + 2)[0] and w.lockout is None


def test_enabled_but_firmware_missing_blocks(tmp_path):
    w = g(tmp_path, leakSensorEnabled=True, lowWaterSensorEnabled=True)
    w.observe_sensors(None, None, T0)
    ok, why = w.check(1000, "auto", T0)
    assert not ok and "PIN_LEAK" in why
