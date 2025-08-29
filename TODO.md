# TODO

### Protocol Grid
- include n_samples as a field for protocol run data results. Protocol data logging implemented in protocol_grid/services/protocol_data_logger.py and used in protocol_grid/services/protocol_runner_controller.py
- [Bug] incorrect model rebuild while changing voltage/freq while running in advanced mode. This bug makes all rows to have empty Voltage and Frequency values when changing any one row's Voltage or Frequency DURING A PROTOCOL RUN IN ADVANCED USER MODE. 