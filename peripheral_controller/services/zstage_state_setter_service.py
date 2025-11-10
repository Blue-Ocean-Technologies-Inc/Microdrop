from functools import wraps

from traits.api import provides, HasTraits, Instance

from microdrop_utils.dramatiq_peripheral_serial_proxy import DramatiqPeripheralSerialProxy

from ..interfaces.i_peripheral_control_mixin_service import IPeripheralControlMixinService

from logger.logger_service import get_logger
logger = get_logger(__name__)

# silence all APScheduler job-exception logs
get_logger('apscheduler.executors.default').setLevel(level="WARNING")

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
    Decorator to log a method call and wrap it in the instance's
    proxy transaction lock.
    """

    @wraps(func)
    def wrapped(self, *args, **kwargs):
        logger.info("Enable Motor")
        self.proxy.zstage.motor_enabled = True

        try:
            result = func(self, *args, **kwargs)

        finally:
            logger.info(f"Method {func.__name__} finished. New position: {self.proxy.zstage.position}")
            logger.info("Disable Motor")
            self.proxy.zstage.motor_enabled = False

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
    def on_go_home_request(self, message):
        """
        Home z stage
        """

    @thread_lock_with_error_handling
    @zstage_motor_context
    def on_move_up_request(self, message):
        """
        Move up z stage
        """
        self.proxy.zstage.up()

    @thread_lock_with_error_handling
    @zstage_motor_context
    def on_move_down_request(self, message):
        """
        Move down z stage
        """
        self.proxy.zstage.down()

    @thread_lock_with_error_handling
    @zstage_motor_context
    def on_set_position_request(self, message):
        """
        Move z stage to position.
        """
        self.proxy.zstage.position = float(message)