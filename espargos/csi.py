from typing import TypedDict
import numpy as np
import ctypes

from . import constants

# Internal constants
_ESPARGOS_SPI_BUFFER_SIZE = 512
_ESPARGOS_SPI_TYPE_HEADER_CSI = 0x5a1f19b1

# Other constants
HT40_GAP_SUBCARRIERS = 3
"Gap between primary and secondary channel in HT40 mode, in subcarriers"

class wifi_pkt_rx_ctrl_t(ctypes.LittleEndianStructure):
    """
    A ctypes structure representing the `wifi_pkt_rx_ctrl_t` as provided by the ESP32.
    See the related `esp-idf code <https://github.com/espressif/esp-idf/blob/master/components/esp_wifi/include/local/esp_wifi_types_native.h>`_ for details.
    """
    _pack_ = 1

    _fields_ = [
        ("rssi", ctypes.c_int8, 8),
        ("rate", ctypes.c_uint8, 5),
        ("reserved1", ctypes.c_uint8, 1),
        ("sig_mode", ctypes.c_uint8, 2),
        ("reserved2", ctypes.c_uint16, 16),
        ("mcs", ctypes.c_uint8, 7),
        ("cwb", ctypes.c_uint8, 1),
        ("reserved3", ctypes.c_uint16, 16),
        ("smoothing", ctypes.c_uint8, 1),
        ("not_sounding", ctypes.c_uint8, 1),
        ("reserved4", ctypes.c_uint8, 1),
        ("aggregation", ctypes.c_uint8, 1),
        ("stbc", ctypes.c_uint8, 2),
        ("fec_coding", ctypes.c_uint8, 1),
        ("sgi", ctypes.c_uint8, 1),
        ("reserved5", ctypes.c_uint8, 8),
        ("ampdu_cnt", ctypes.c_uint8, 8),
        ("channel", ctypes.c_uint8, 4),
        ("secondary_channel", ctypes.c_uint8, 4),
        ("rxstart_time_cyc", ctypes.c_uint8, 7),
        ("reserved6", ctypes.c_uint8, 1),
        ("timestamp", ctypes.c_uint32, 32),
        ("reserved7", ctypes.c_uint32, 32),
        ("reserved8", ctypes.c_uint32, 32),
        ("reserved9", ctypes.c_uint32, 20),
        ("rxstart_time_cyc_dec", ctypes.c_uint32, 11),
        ("ant", ctypes.c_uint8, 1),
        ("noise_floor", ctypes.c_int8, 8),
        ("reserved10", ctypes.c_uint32, 24),
        ("sig_len", ctypes.c_uint16, 12),
        ("reserved11", ctypes.c_uint16, 12),
        ("rx_state", ctypes.c_uint8, 8),
    ]

    def __new__(self, buf=None):
        if buf:
            buf = bytearray(buf)
            buf.append(0)  # zero-pad to fix a bug, see below
        return self.from_buffer_copy(buf)

    def __init__(self, buf=None):
        pass


# Bug in ctypes, see https://bugs.python.org/issue29753 and https://github.com/python/cpython/pull/19850, need to manually specify size
# We need to write some hacky workarounds here...
wifi_pkt_rx_ctrl_t_size = ctypes.sizeof(wifi_pkt_rx_ctrl_t)  # = 37
wifi_pkt_rx_ctrl_t_size = 36

# 0-5: lltf_guard_below
# 6-58: lltf
# 60-65: lltf_guard_above
# 66-122: htltf primary
# 123-133: htltf_guard
# 134-190: htltf secondary
class csi_buf_t(ctypes.LittleEndianStructure):
    """
    A ctypes structure representing the CSI buffer as produced by the ESP32.

    This structure is used to store the channel coefficients estimated from Wi-Fi packets,
    directly as provided in the :code:`buf` field of :code:`wifi_csi_info_t` by esp-idf, refer to the related `esp-idf documentation <https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/wifi.html#wi-fi-channel-state-information>`_ for details.
    The structure is packed to ensure there is no padding between fields.
    """
    _pack_ = 1
    _fields_ = [
        ("lltf_guard_below", ctypes.c_int8 * (6 * 2)), # all zeros
        ("lltf", ctypes.c_int8 * (53 * 2)),
        ("lltf_guard_above", ctypes.c_int8 * (7 * 2)), # all zeros
        ("htltf_higher",  ctypes.c_int8 * (57 * 2)),
        ("htltf_guard",  ctypes.c_int8 * (11 * 2)), # all zeros
        ("htltf_lower",  ctypes.c_int8 * (57 * 2))
    ]

    def __new__(self, buf=None):
        return self.from_buffer_copy(buf)

    def __init__(self, buf=None):
        pass

class seq_ctrl_t(ctypes.LittleEndianStructure):
    """
    A ctypes structure representing the sequence control field of a Wi-Fi packet.

    This structure is used to store the sequence control field of a Wi-Fi packet, which contains the fragment number and the segment number.
    """
    _pack_ = 1
    _fields_ = [
        ("frag", ctypes.c_uint8, 4),
        ("seg", ctypes.c_uint16, 12)
    ]

    def __new__(self, buf=None):
        return self.from_buffer_copy(buf)

    def __init__(self, buf=None):
        pass

class serialized_csi_t(ctypes.LittleEndianStructure):
    """
    A ctypes structure representing the CSI buffer and metadata as provided by the ESPARGOS firmware.
    """
    _pack_ = 1
    _fields_ = [
        ("type_header", ctypes.c_uint32),
        ("rx_ctrl", ctypes.c_uint8 * wifi_pkt_rx_ctrl_t_size),
        ("source_mac", ctypes.c_uint8 * 6),
        ("dest_mac", ctypes.c_uint8 * 6),
        ("seq_ctrl", seq_ctrl_t),
        ("timestamp", ctypes.c_uint32),
        ("is_calib", ctypes.c_bool),
        ("first_word_invalid", ctypes.c_bool),
        ("buf", ctypes.c_int8 * (ctypes.sizeof(csi_buf_t)))
    ]

    def __new__(self, buf=None):
        return self.from_buffer_copy(buf)

    def __init__(self, buf=None):
        pass

class csistream_pkt_t(ctypes.LittleEndianStructure):
    """
    A ctypes structure representing a CSI packet as received from the ESPARGOS controller, i.e.,
    sensor number and the raw data buffer that should contain the serialized_csi_t structure if the type_header matches.
    """
    _pack_ = 1
    _fields_ = [
        ("esp_num", ctypes.c_uint32),
        ("buf", ctypes.c_uint8 * _ESPARGOS_SPI_BUFFER_SIZE),
    ]

    def __new__(self, buf=None):
        return self.from_buffer_copy(buf)

    def __init__(self, buf=None):
        pass