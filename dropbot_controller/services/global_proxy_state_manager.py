import threading
import time
import numpy as np
from typing import Optional, Dict, Any, Callable
from traits.api import HasTraits, Instance, Bool, Int, Float, Any as TraitsAny
from microdrop_utils._logger import get_logger
from microdrop_utils.dramatiq_dropbot_serial_proxy import DramatiqDropbotSerialProxy

logger = get_logger(__name__, level="DEBUG")


class GlobalProxyStateManager(HasTraits):
    """
    Global proxy state manager to prevent channel corruption and coordinate access across all services.
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    proxy = Instance(object, allow_none=True)
    _expected_channels = Int(120)
    _last_valid_state = Instance(np.ndarray, allow_none=True)
    _last_validation_time = Float(0.0)
    _validation_interval = Float(2.0)
    _corruption_count = Int(0)
    _max_corruption_retries = Int(3)
    _state_recovery_in_progress = Bool(False)
    _proxy_reconnection_in_progress = Bool(False)
    _last_port_name = TraitsAny()  # Store last known port for reconnection
    
    def __new__(cls, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, **traits):
        if hasattr(self, '_initialized'):
            return
        super().__init__(**traits)
        self._initialized = True
        logger.info("Global ProxyStateManager created")
    
    def set_proxy(self, proxy, port_name=None):
        """Set the proxy instance and validate it."""
        if proxy and hasattr(proxy, 'transaction_lock'):
            with proxy.transaction_lock:
                self.proxy = proxy
                if port_name:
                    self._last_port_name = port_name
                self._validate_and_cache_state()
                logger.info("Proxy set in global state manager")
        else:
            self.proxy = proxy
            if port_name:
                self._last_port_name = port_name
            if proxy:
                self._validate_and_cache_state()
    
    def validate_proxy_state(self) -> bool:
        """Validate proxy state and attempt recovery if corrupted."""
        if not self.proxy:
            logger.error("Proxy not available for validation")
            return False
        
        current_time = time.time()
        
        # Rate limit validation checks
        if current_time - self._last_validation_time < self._validation_interval:
            return True
        
        self._last_validation_time = current_time
        
        try:
            # Use proxy's own transaction lock if available
            if hasattr(self.proxy, 'transaction_lock'):
                with self.proxy.transaction_lock:
                    return self._perform_validation()
            else:
                return self._perform_validation()
        except Exception as e:
            logger.error(f"Critical error during proxy validation: {e}")
            return self._attempt_proxy_recovery()
    
    def _perform_validation(self) -> bool:
        """Perform the actual validation logic."""
        try:
            # Check basic proxy properties
            channel_count = self.proxy.number_of_channels
            if channel_count != self._expected_channels:
                logger.error(f"Channel count corrupted: {channel_count}, expected {self._expected_channels}")
                return self._attempt_proxy_recovery()
            
            # Check state consistency
            current_state = self.proxy.state_of_channels
            if len(current_state) != channel_count:
                logger.error(f"State length mismatch: {len(current_state)} != {channel_count}")
                return self._attempt_proxy_recovery()
            
            # Cache valid state for recovery
            self._last_valid_state = np.copy(current_state)
            self._corruption_count = 0
            return True
            
        except Exception as e:
            logger.error(f"Proxy validation error: {e}")
            return self._attempt_proxy_recovery()
    
    def _attempt_proxy_recovery(self) -> bool:
        """Attempt to recover from proxy state corruption."""
        if self._state_recovery_in_progress or self._proxy_reconnection_in_progress:
            logger.warning("Recovery already in progress")
            return False
        
        self._state_recovery_in_progress = True
        self._corruption_count += 1
        
        try:
            if self._corruption_count > self._max_corruption_retries:
                logger.error(f"Max corruption retries exceeded ({self._max_corruption_retries}), attempting full reconnection")
                return self._attempt_proxy_reconnection()
            
            logger.info(f"Attempting proxy state recovery (attempt {self._corruption_count})")
            
            # Method 1: Try to reinitialize switching boards
            try:
                if hasattr(self.proxy, 'initialize_switching_boards'):
                    self.proxy.initialize_switching_boards()
                    logger.info("Switching boards reinitialized")
                    
                    # Validate after reinitialization
                    if self.proxy.number_of_channels == self._expected_channels:
                        logger.info("State recovery successful via switching board reinitialization")
                        self._corruption_count = 0
                        return True
            except Exception as e:
                logger.warning(f"Switching board reinitialization failed: {e}")
            
            # Method 2: Try to restore last known good state
            if self._last_valid_state is not None:
                try:
                    self.proxy.state_of_channels = self._last_valid_state
                    logger.info("State recovery attempted via last valid state restoration")
                    return True
                except Exception as e:
                    logger.warning(f"State restoration failed: {e}")
            
            # Method 3: Force full reconnection
            logger.warning("Standard recovery methods failed, attempting full reconnection")
            return self._attempt_proxy_reconnection()
            
        finally:
            self._state_recovery_in_progress = False
    
    def _attempt_proxy_reconnection(self) -> bool:
        """Attempt complete proxy reconnection as last resort."""
        if self._proxy_reconnection_in_progress:
            logger.warning("Proxy reconnection already in progress")
            return False
        
        if not self._last_port_name:
            logger.error("No port name available for reconnection")
            return False
        
        logger.info(f"Attempting complete proxy reconnection to port {self._last_port_name}")
        self._proxy_reconnection_in_progress = True
        
        try:
            # Terminate current proxy
            if self.proxy and hasattr(self.proxy, 'terminate'):
                try:
                    self.proxy.terminate()
                    logger.info("Old proxy terminated")
                except Exception as e:
                    logger.warning(f"Error terminating old proxy: {e}")
            
            # Small delay for port to settle
            time.sleep(0.5)
            
            # Create new proxy
            new_proxy = DramatiqDropbotSerialProxy(port=self._last_port_name)
            logger.info(f"New proxy created for port {self._last_port_name}")
            
            # Initialize new proxy
            new_proxy.initialize_switching_boards()
            
            # Validate new proxy
            if new_proxy.number_of_channels == self._expected_channels:
                self.proxy = new_proxy
                self._corruption_count = 0
                self._last_valid_state = np.copy(new_proxy.state_of_channels)
                logger.info("Proxy reconnection successful")
                
                # Notify about reconnection success
                from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
                from dropbot_controller.consts import DROPBOT_CONNECTED
                publish_message('proxy_reconnected', DROPBOT_CONNECTED)
                
                return True
            else:
                logger.error(f"New proxy has wrong channel count: {new_proxy.number_of_channels}")
                new_proxy.terminate()
                return False
                
        except Exception as e:
            logger.error(f"Proxy reconnection failed: {e}")
            return False
        finally:
            self._proxy_reconnection_in_progress = False
    
    def _validate_and_cache_state(self):
        """Initial validation and caching of proxy state."""
        try:
            if self.proxy and hasattr(self.proxy, 'number_of_channels'):
                if self.proxy.number_of_channels == self._expected_channels:
                    self._last_valid_state = np.copy(self.proxy.state_of_channels)
                    logger.debug("Initial proxy state cached")
        except Exception as e:
            logger.warning(f"Initial state caching failed: {e}")
    
    def safe_proxy_access(self, operation_name: str, timeout: float = 5.0):
        """Context manager for safe proxy access with timeout and validation."""
        return SafeProxyContext(self, operation_name, timeout)
    
    @classmethod
    def get_instance(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class SafeProxyContext:
    """Context manager for safe proxy operations."""
    
    def __init__(self, state_manager: GlobalProxyStateManager, operation_name: str, timeout: float):
        self.state_manager = state_manager
        self.operation_name = operation_name
        self.timeout = timeout
        self.transaction_lock_acquired = False
    
    def __enter__(self):
        # Validate state before operation
        if not self.state_manager.validate_proxy_state():
            logger.error(f"Proxy state validation failed before {self.operation_name}")
            raise RuntimeError(f"Proxy state corrupted before {self.operation_name}")
        
        # Use proxy's transaction lock if available
        if (self.state_manager.proxy and 
            hasattr(self.state_manager.proxy, 'transaction_lock')):
            
            if self.state_manager.proxy.transaction_lock.acquire(timeout=self.timeout):
                self.transaction_lock_acquired = True
                return self.state_manager.proxy
            else:
                raise TimeoutError(f"Could not acquire proxy transaction lock for {self.operation_name}")
        else:
            return self.state_manager.proxy
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.transaction_lock_acquired:
            try:
                # Validate state after operation if no exception
                if exc_type is None:
                    self.state_manager.validate_proxy_state()
            finally:
                self.state_manager.proxy.transaction_lock.release()