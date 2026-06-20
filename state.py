class LoopState:
    """In-memory state tracked across loop iterations."""

    def __init__(self):
        self.last_process_time = 0  # Unix epoch seconds; initial = epoch 0
        self.last_settings = None   # dict: {"mode", "base_temp", "rooms"}

    def update(self, process_time, settings):
        """Update state after a loop iteration.

        Args:
            process_time: Unix epoch seconds from HTTP Date header.
            settings: dict with mode, base_temp, rooms.
        """
        self.last_process_time = process_time
        self.last_settings = settings
