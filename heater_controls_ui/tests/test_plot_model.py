"""Hardware-free tests for the heater plot telemetry extractor + model."""
from heater_controls_ui.telemetry import telemetry_samples
from heater_controls_ui.plots.model import HeaterPlotModel
from heater_controls_ui.plots.consts import MAX_PLOT_POINTS


# --- telemetry_samples ------------------------------------------------------

def test_samples_temp_frame_returns_numeric_temperatures():
    data = {"_frame": "TEMP", "temperatures": {"inlet": 25.5, "outlet": 30.0}}
    assert telemetry_samples(data) == {
        "temperatures": {"inlet": 25.5, "outlet": 30.0}}


def test_samples_pid_frame_returns_heater_pid_and_pwm():
    data = {"_frame": "PID_TEC1", "pid_temperature": 41.2, "pwm_percentage": 30}
    assert telemetry_samples(data) == {
        "heater": "tec1", "pid_temperature": 41.2, "pwm_percentage": 30.0}


def test_samples_drops_sentinel_temperatures():
    assert telemetry_samples(
        {"_frame": "TEMP", "temperatures": {"inlet": -127.0}}) == {}
    pid = telemetry_samples(
        {"_frame": "PID_TEC1", "pid_temperature": -127.0, "pwm_percentage": 0})
    assert pid == {"heater": "tec1", "pwm_percentage": 0.0}   # temp omitted


def test_samples_ignores_non_plottable_frames():
    assert telemetry_samples({"_frame": "WHOAMI", "device_id": "x"}) == {}
    assert telemetry_samples({"_frame": "ERR", "kind": "overtemp"}) == {}


# --- HeaterPlotModel --------------------------------------------------------

def test_sample_is_noop_before_any_data():
    m = HeaterPlotModel()
    m.sample(now=1.0)
    times, sensors, pids, pwms = m.snapshot()
    assert times == [] and sensors == {} and pids == {} and pwms == {}


def test_sample_and_hold_aligns_series_to_timeline():
    m = HeaterPlotModel()
    m.apply({"temperatures": {"inlet": 25.0}})
    m.sample(now=0.0)                                   # t=0
    m.apply({"heater": "tec1", "pid_temperature": 40.0, "pwm_percentage": 50.0})
    m.sample(now=1.0)                                   # t=1
    times, sensors, pids, pwms = m.snapshot()
    assert times == [0.0, 1.0]
    assert sensors["inlet"] == [25.0, 25.0]             # held across the 2nd tick
    assert pids["tec1"] == [None, 40.0]                 # back-filled before it appeared
    assert pwms["tec1"] == [None, 50.0]


def test_clear_resets_everything():
    m = HeaterPlotModel()
    m.apply({"temperatures": {"inlet": 25.0}})
    m.sample(now=0.0)
    m.clear()
    assert m.snapshot() == ([], {}, {}, {})


def test_rolling_window_caps_history():
    m = HeaterPlotModel()
    m.apply({"temperatures": {"inlet": 25.0}})
    for i in range(MAX_PLOT_POINTS + 50):
        m.sample(now=float(i))
    times, sensors, _pids, _pwms = m.snapshot()
    assert len(times) == MAX_PLOT_POINTS
    assert len(sensors["inlet"]) == MAX_PLOT_POINTS
    assert times[-1] == float(MAX_PLOT_POINTS + 49)     # newest retained
