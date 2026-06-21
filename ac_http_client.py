"""Public skeleton for the air conditioner HTTP client module.

This file intentionally omits internal implementation details.
"""

VALID_ROOM_VALUES = {0, 1, 2}
DEFAULT_MANUAL_CTRL_ID = 1000


def _skeleton_only(name):
    raise NotImplementedError(f"{name} is intentionally omitted in the public skeleton.")


def _json_dumps(value):
    _skeleton_only("_json_dumps")


class AcHttpClient:
    """Air Conditioner HTTP Client skeleton."""

    def __init__(
        self,
        base_url,
        room_id,
        room_info_id,
        timeout=10,
        manual_ctrl_id=DEFAULT_MANUAL_CTRL_ID,
    ):
        self.base_url = base_url
        self.room_id = room_id
        self.room_info_id = room_info_id
        self.timeout = timeout
        self.manual_ctrl_id = manual_ctrl_id

    def set_base_temp(self, temp):
        _skeleton_only("AcHttpClient.set_base_temp")

    def set_heat(self):
        _skeleton_only("AcHttpClient.set_heat")

    def set_cool(self):
        _skeleton_only("AcHttpClient.set_cool")

    def set_auto_save(self):
        _skeleton_only("AcHttpClient.set_auto_save")

    def set_room_adjust(self, adjust, mode=None, current_cool_flg=None):
        _skeleton_only("AcHttpClient.set_room_adjust")

    def get_current_state(self):
        _skeleton_only("AcHttpClient.get_current_state")
