import json
import time
from functools import wraps
from pydantic import ValidationError

from traits.api import provides, HasTraits, Instance

from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from ..interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService
from ..datamodels import ZStageConfigData
from ..consts import ZSTAGE_POSITION_UPDATED, MIN_ZSTAGE_HEIGHT_MM, MAGNET_APPLIED
from ..preferences import PeripheralPreferences

from logger.logger_service import get_logger
logger = get_logger(__name__)


def thread_lock_with_error_handling(func):
    """
    Decorator to log a method call and wrap it in the instance's
    proxy transaction lock.
    """

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        # 'self' will be the instance of ZStageStatesSetterMixinService
        logger.info(f"Calling method: {func.__name__} with args={args}, kwargs={kwargs}")

        try:
            # Access the proxy from the instance
            with self.proxy.transaction_lock:
                # Call the original method, passing 'self' and all other args
                result = func(self, *args, **kwargs)

            return result

        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise

    return wrapped

def zstage_motor_context(func):
    """
    enable zstage motor and then turn off.
    """

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        logger.info("Enabled Motor")
        self.proxy.zstage.motor_enabled = True

        try:
            result = func(self, *args, **kwargs)

        finally:
            logger.info("Disabled Motor")
            self.proxy.zstage.motor_enabled = False

        return result

    return wrapped

def publish_position_update(func):
    """
    After position change, publish_update
    """

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        ols_pos = self.proxy.zstage.position

        try:
            result = func(self, *args, **kwargs)

        finally:
            new_pos = self.proxy.zstage.position
            if new_pos != ols_pos:
                publish_message(f"{new_pos}", ZSTAGE_POSITION_UPDATED)

            logger.info(f"Method {func.__name__} finished. Positions -> new: {self.proxy.zstage.position}, old: {ols_pos}")

        return result

    return wrapped


#####################################################################################
@provides(IPeripheralControlMixinService)
class ZStageStatesSetterMixinService(HasTraits):
    """
    A mixin Class that adds methods to set states on a peripheral z-stage.
    """
    proxy = Instance(DramatiqPeripheralSerialProxy)

    ######################################## Methods to Expose #############################################

    ################################### Exposed Methods ###############################

    @thread_lock_with_error_handling
    @zstage_motor_context
    @publish_position_update
    def on_go_home_request(self, message):
        """
        Home z stage
        """
        self.proxy.zstage.home()

    @thread_lock_with_error_handling
    @zstage_motor_context
    @publish_position_update
    def on_move_up_request(self, message):
        """
        Move up z stage
        """
        self.proxy.zstage.up()

    @thread_lock_with_error_handling
    @zstage_motor_context
    @publish_position_update
    def on_move_down_request(self, message):
        """
        Move down z stage
        """
        self.proxy.zstage.down()

    @thread_lock_with_error_handling
    @zstage_motor_context
    @publish_position_update
    def on_set_position_request(self, message):
        """
        Move z stage to position.
        """
        self.proxy.zstage.position = float(message)

    @thread_lock_with_error_handling
    @zstage_motor_context
    @publish_position_update
    def on_protocol_set_magnet_request(self, message):
        """Protocol-driven magnet engage/retract. Atomic: handles the
        retract sequence (MOVE_DOWN + 0.3s settle + GO_HOME) on the
        backend so the protocol handler only does one publish + one
        wait_for. On hardware error, ack is NOT published — protocol's
        wait_for times out and the step fails (consistent with PPT-4's
        protocol handler pattern).
        """
        try:
            payload = json.loads(message)
            on = bool(payload["on"])
            height_mm = float(payload["height_mm"])

            if not on:
                # Retract sequence — matches legacy publish_magnet_home()
                self.proxy.zstage.down()
                time.sleep(0.3)   # settling time before next command
                self.proxy.zstage.home()
            elif height_mm < MIN_ZSTAGE_HEIGHT_MM:
                # Sentinel = "use live pref" (preserves legacy 'Default'
                # behaviour: pref changes affect 'Default' steps without
                # re-editing the protocol).
                target = PeripheralPreferences().up_height_mm
                self.proxy.zstage.position = float(target)
            else:
                self.proxy.zstage.position = float(height_mm)

            publish_message(topic=MAGNET_APPLIED, message=str(int(on)))
        except (TimeoutError, RuntimeError) as e:
            logger.error(f"Proxy error on protocol_set_magnet: {e}")
        except Exception as e:
            logger.error(f"Error on protocol_set_magnet: {e}")
            raise

    @thread_lock_with_error_handling
    def on_update_config_request(self, message):
        """
        Move z stage to position.
        """
        # 1. Validate and Parse
        # model_validate_json takes the raw JSON string/bytes, parses it,
        # and runs all your checks (floats, no extra fields, up > down).

        try:
            validated_config = ZStageConfigData.model_validate_json(message)

            # 2. Pass to Proxy
            # Use .model_dump() to convert the model instance back to a dictionary
            # so you can unpack it with **
            config = validated_config.model_dump(exclude_none=True)
            logger.critical(f"Attempting to set Z-stage config: {config}")

            self.proxy.update_config(**config)

            logger.critical(f"Success: Z-stage config changed to: {self.proxy.config}")

        except Exception as e:
            logger.error(
                f"Could not process zstage config updates. Message was {message}.\n"
                f"Error: {e}",
                exc_info=True
            )

