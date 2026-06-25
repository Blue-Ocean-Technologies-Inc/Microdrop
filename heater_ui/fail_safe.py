# -*- coding: utf-8 -*-
def fail_safe(func):
    def func_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)

        except Exception as e:
            self = args[0]

            # Build detailed traceback info to point to the exact location
            import linecache
            tb = e.__traceback__
            deepest = None
            while tb is not None:
                deepest = tb
                tb = tb.tb_next
            if deepest is not None:
                filename = deepest.tb_frame.f_code.co_filename
                lineno = deepest.tb_lineno
                func_name = deepest.tb_frame.f_code.co_name
                offending_line = (
                    linecache.getline(filename, lineno).rstrip()
                )
                location_info = (
                    f"{filename}:{lineno} in {func_name} -> {offending_line}"
                )
            else:
                location_info = "<no traceback available>"

            error_msg = (
                f"[{e.__class__.__name__}] {e} | {location_info}"
            )
            # Log as error to be consistent and visible
            if hasattr(self, 'logger'):
                self.logger.error(error_msg, exc_info=True)

            # Update UI status bar if available (concise message)
            ui_msg = f"Error: {e}"
            if hasattr(self, 'ui') and hasattr(self.ui, 'statusbar'):
                # Show for 5 seconds
                self.ui.statusbar.showMessage(ui_msg, 5000)
            elif hasattr(self, 'status_message') and callable(
                getattr(self, 'status_message', None)
            ):
                self.status_message.emit(ui_msg)

            # Return appropriate value based on function signature
            # For boolean functions, return False
            # For other functions, return None or empty values
            import inspect
            return_annotation = inspect.signature(func).return_annotation
            if return_annotation == bool:
                return False
            elif return_annotation == dict:
                return {}
            elif return_annotation == list:
                return []
            elif return_annotation == str:
                return ""
            else:
                return None

    return func_wrapper
