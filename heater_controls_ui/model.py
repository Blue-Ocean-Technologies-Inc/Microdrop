from traits.api import HasTraits, Bool, List, Str, Float, Range, Button


class HeaterControlModel(HasTraits):
    """Qt-free state for the heater controls dock pane.

    The connection/telemetry listener writes the status fields and the available
    heater channels; the dock-pane controller reads the inputs and reacts to the
    command buttons. Nothing here touches Qt or dramatiq.
    """

    # -- Connection ----------------------------------------------------------
    connected = Bool(False, desc="True when the heater backend reports connected")

    # -- Heater channel selection (dropdown is populated from the board) ------
    available_heaters = List(Str, desc="Channels reported by the board")
    selected_heater = Str(desc="Channel that commands target")

    # -- Command inputs ------------------------------------------------------
    temperature = Float(40.0, desc="PID setpoint to apply (C)")
    pwm = Range(value=0, low=0, high=100, desc="Open-loop duty to apply (%)")
    stream_group = Str("all", desc="Sensor group to stream")

    # -- Command buttons -----------------------------------------------------
    apply_temperature = Button("Set Temp")
    apply_pwm = Button("Set PWM")
    pid_enable = Button("Enable")
    pid_disable = Button("Disable")
    pid_stop = Button("Stop")
    stream_start = Button("Start Stream")
    stream_stop = Button("Stop Stream")
    fan_on = Button("Fan On")
    fan_off = Button("Fan Off")
    all_off = Button("All Off")
    connect = Button("Search Connection")

    # -- Status readouts (written by the listener) ---------------------------
    status_text = Str("Disconnected")
    board_id_text = Str("Board: —")
    pid_temp_text = Str("PID temp: —")
    pwm_text = Str("PWM: —")
    temps_text = Str("Temps: —")
