"""Live temperature / PWM plotting dock pane for the heater UI.

A self-contained pane that taps the heater telemetry stream and draws rolling
Temperature and PWM charts (matplotlib), styled with the microdrop_style brand
palette. Kept decoupled from the status pane: it runs its own telemetry
listener and owns its own Qt-free plot model.
"""
