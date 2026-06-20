import ujson as json
import urequests as requests

# NOTE: This is a skeleton implementation. The actual implementation details have been removed.

VALID_ROOM_VALUES = {0, 1, 2, 3, 4, 255}


class AcHttpClient:
    """Air Conditioner HTTP Client.

    Communicates with the air conditioning controller via HTTP to
    read current status and send control commands (mode, temperature,
    room offsets).
    """

    def __init__(self, base_url, room_id, room_info_id, timeout=10):
        self.base_url = base_url.rstrip("/")
        self.room_id = room_id
        self.room_info_id = room_info_id
        self.timeout = timeout

    def set_base_temp(self, temp):
        raise NotImplementedError()

    def set_auto_steady(self):
        raise NotImplementedError()

    def set_auto_save(self):
        raise NotImplementedError()

    def set_room_adjust(self, adjust):
        raise NotImplementedError()

    def get_current_state(self):
        raise NotImplementedError()
