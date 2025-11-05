import time

from microdrop_utils.hardware_device_monitoring_helpers import check_devices_available

magnetic_state_hwids = ['VID:PID=0403:6015']
port = check_devices_available(magnetic_state_hwids)

print(port)

from mr_box_peripheral_board import SerialProxy

settling_time_s = 2.5

proxy = SerialProxy(port=port)

time.sleep(settling_time_s)

print(proxy.config)

down_height = proxy.config.zstage_down_position
up_height = proxy.config.zstage_up_position

zstage = proxy.zstage

## ensure zstage is homed
zstage.home()
print(zstage.position == down_height)
print(zstage.is_down == True)
print(zstage.is_up == False)
time.sleep(0.5)

## bring stage up
zstage.up()
print(zstage.position == up_height)
print(zstage.is_up == True)
print(zstage.is_down == False)

# bring stage down
zstage.down()
print(zstage.position == down_height)
print(zstage.is_down == True)
print(zstage.is_up == False)

time.sleep(0.5)
# home again
zstage.home()

proxy.terminate()





