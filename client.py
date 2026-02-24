class AirLohasClient:
    """Public skeleton for publication.

    This file intentionally omits the production communication logic.
    Implement each method in your private repository.
    """

    def __init__(self, base_url, room_id, room_info_id, timeout=10):
        self.base_url = base_url
        self.room_id = room_id
        self.room_info_id = room_info_id
        self.timeout = timeout

    def set_base_temp(self, temp):
        raise NotImplementedError("set_base_temp is not included in the public skeleton")

    def set_auto_steady(self):
        raise NotImplementedError("set_auto_steady is not included in the public skeleton")

    def set_auto_save(self):
        raise NotImplementedError("set_auto_save is not included in the public skeleton")

    def set_room_adjust(self, adjust):
        raise NotImplementedError("set_room_adjust is not included in the public skeleton")

    def get_current_state(self):
        raise NotImplementedError("get_current_state is not included in the public skeleton")
