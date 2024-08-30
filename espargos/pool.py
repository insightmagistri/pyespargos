#!/usr/bin/env python3

from collections import OrderedDict
import numpy as np
import threading
import binascii
import logging
import ctypes
import time

from espargos import board

from . import constants
from . import util
from . import csi

class ClusteredCSI(object):
    def __init__(self, source_mac, dest_mac, seq_ctrl, boardcount):
        self.source_mac = source_mac
        self.dest_mac = dest_mac
        self.timestamp = time.time()
        self.seq_ctrl = seq_ctrl
        self.boardcount = boardcount
        self.serialized_csi_all = [[[None for c in range(constants.ANTENNAS_PER_ROW)] for r in range(constants.ROWS_PER_BOARD)] for b in range(self.boardcount)]
        self.shape = (self.boardcount, constants.ROWS_PER_BOARD, constants.ANTENNAS_PER_ROW)
        self.csi_completion_state = np.full(self.shape, False)
        self.csi_completion_state_all = False
        self.complex_csi_all = np.full(self.shape + (ctypes.sizeof(csi.csi_buf_t) // 2, ), fill_value = np.nan, dtype = np.complex64)
        self.complex_csi_lltf = self.complex_csi_all[:,:,:,csi.csi_buf_t.lltf.offset // 2:(csi.csi_buf_t.lltf.offset + csi.csi_buf_t.lltf.size) // 2].view()
        self.complex_csi_htltf_higher = self.complex_csi_all[:,:,:,csi.csi_buf_t.htltf_higher.offset // 2:(csi.csi_buf_t.htltf_higher.offset + csi.csi_buf_t.htltf_higher.size) // 2].view()
        self.complex_csi_htltf_lower = self.complex_csi_all[:,:,:,csi.csi_buf_t.htltf_lower.offset // 2:(csi.csi_buf_t.htltf_lower.offset + csi.csi_buf_t.htltf_lower.size) // 2].view()
        self.rssi_all = np.full(self.shape, fill_value = np.nan, dtype = np.float32)

    def foreach_complete_sensor(self, cb):
        for b, board in enumerate(self.serialized_csi_all):
            for r, row in enumerate(board):
                for a, serialized_csi in enumerate(row):
                    if serialized_csi is not None:
                        cb(b, r, a, serialized_csi)

    def first_complete_sensor(self):
        for board in self.serialized_csi_all:
            for row in board:
                for serialized_csi in row:
                    if serialized_csi is not None:
                        return serialized_csi

        return None

    def add_csi(self, board_num, esp_num, serialized_csi, csi_cplx):
        row = 1 - esp_num // 4
        column = 3 - esp_num % 4
        self.serialized_csi_all[board_num][row][column] = serialized_csi
        self.complex_csi_all[board_num, row, column] = csi_cplx
        self.csi_completion_state[board_num, row, column] = True
        self.csi_completion_state_all = np.all(self.csi_completion_state)
        self.rssi_all[board_num, row, column] = csi.wifi_pkt_rx_ctrl_t(serialized_csi.rx_ctrl).rssi


    def deserialize_csi_lltf(self):
        return self.complex_csi_lltf

    def deserialize_csi_ht40(self):
        assert(self.is_ht40())
        loc = self.get_secondary_channel_relative()
        assert(loc != 0)

        csi_ht40 = np.zeros(self.shape + ((csi.csi_buf_t.htltf_lower.size + csi.HT40_GAP_SUBCARRIERS * 2 + csi.csi_buf_t.htltf_higher.size) // 2,), dtype = np.complex64)
        csi_higher = csi_ht40[:,:,:,:csi.csi_buf_t.htltf_lower.size // 2].view()
        csi_lower = csi_ht40[:,:,:,-csi.csi_buf_t.htltf_higher.size // 2:].view()
        csi_higher[:] = self.complex_csi_htltf_lower
        csi_lower[:] = self.complex_csi_htltf_higher

        # Secondary channel experiences phase shift by pi / 2
        # This is likely due to the pi / 2 phase shift specified for the pilot symbols,
        # see IEEE 80211-2012 section 20.3.9.3.4 L-LTF definition
        if loc == 1:
            csi_higher = csi_higher * np.exp(-1.0j * np.pi / 2)
        else:
            csi_lower = csi_lower * np.exp(-1.0j * np.pi / 2)

        return csi_ht40

    def is_ht40(self):
        return csi.wifi_pkt_rx_ctrl_t(self.first_complete_sensor().rx_ctrl).cwb == 1

    def get_secondary_channel_relative(self):
        match csi.wifi_pkt_rx_ctrl_t(self.first_complete_sensor().rx_ctrl).secondary_channel:
            case 0:
                return 0
            case 1:
                return 1
            case 2:
                return -1

    def get_primary_channel(self):
        return csi.wifi_pkt_rx_ctrl_t(self.first_complete_sensor().rx_ctrl).channel

    def get_secondary_channel(self):
        return self.get_primary_channel() + 4 * self.get_secondary_channel_relative()

    def get_completion(self):
        return self.csi_completion_state

    def get_completion_all(self):
        return self.csi_completion_state_all

    def get_age(self):
        return time.time() - self.timestamp

    def get_sensor_timestamps(self):
        sensor_timestamps = np.full(self.shape, np.nan)

        def append_sensor_timestamp(b, r, a, serialized_csi):
            # Sensor timestamp is in microseconds, but we want it in seconds
            sensor_timestamps[b, r, a] = serialized_csi.timestamp / 1e6

        self.foreach_complete_sensor(append_sensor_timestamp)
        return sensor_timestamps

    def get_host_timestamp(self):
        return self.timestamp

    def get_rssi(self):
        return self.rssi_all

    def get_source_mac(self):
        return self.source_mac

    def get_seq_ctrl(self):
        return self.seq_ctrl

class CSICalibration(object):
    def __init__(self, channel_primary, channel_secondary, calibration_values_ht40, timestamp_calibration_values, board_cable_lengths = None, board_cable_vfs = None):
        # TODO: Handle propagation delay in multi-board setups
        self.channel_primary = channel_primary
        self.channel_secondary = channel_secondary
        wavelengths = util.get_calib_trace_wavelength(util.get_frequencies_ht40(channel_primary, channel_secondary)).astype(calibration_values_ht40.dtype)
        tracelengths = np.asarray(constants.CALIB_TRACE_LENGTH, dtype = calibration_values_ht40.dtype)# - np.asarray(constants.CALIB_TRACE_EMPIRICAL_ERROR)
        prop_calib_each_board = np.exp(-1.0j * 2 * np.pi * tracelengths[:,:,np.newaxis] / wavelengths[np.newaxis, np.newaxis])

        # Account for additional board-specific phase offsets due to different feeder cable lengths in a multi-board antenna array system
        if board_cable_lengths is not None:
            assert(board_cable_vfs is not None)
            board_cable_lengths = np.asarray(board_cable_lengths)
            board_cable_vfs = np.asarray(board_cable_vfs)
            subcarrier_cable_wavelengths = util.get_cable_wavelength(util.get_frequencies_ht40(channel_primary, channel_secondary), board_cable_vfs).astype(calibration_values_ht40.dtype)
            board_phase_offsets = np.exp(-1.0j * 2 * np.pi * board_cable_lengths[:,np.newaxis] / subcarrier_cable_wavelengths)
            prop_calib = np.einsum("bs,ras->bras", board_phase_offsets, prop_calib_each_board)
            coeffs_without_propdelay = np.einsum("bras,bras->bras", calibration_values_ht40, np.conj(prop_calib))
        else:
            coeffs_without_propdelay = np.einsum("bras,ras->bras", calibration_values_ht40, np.conj(prop_calib_each_board))

        self.calibration_values_ht40 = np.exp(-1.0j * np.angle(coeffs_without_propdelay))
        self.calibration_values_ht40_flat = np.sum(np.exp(-1.0j * np.angle(coeffs_without_propdelay)), axis = -1)
        self.timestamp_calibration_values = timestamp_calibration_values

    def apply_ht40(self, values):
        # TODO: Check if primary and secondary channel match
        return np.einsum("bras,bras->bras", values, self.calibration_values_ht40)

    def apply_ht40_flat(self, values):
        # TODO: Check if primary and secondary channel match
        return np.einsum("bras,bra->bras", values, self.calibration_values_ht40_flat)

    def apply_timestamps(self, timestamps):
        return timestamps - self.timestamp_calibration_values

class CSICallback(object):
    def __init__(self, cb, cb_predicate = None):
        # By default, provide csi if CSI is available from all antennas
        self.cb_predicate = cb_predicate
        self.cb = cb
        self.fired = False

    def try_call(self, csi_cluster):
        # Already fired, no need to call callback again
        if self.fired:
            return True

        # Check if callback needs to be called: Use predicate function if defined, otherwise call if all antennas have CSI
        callback_required = False
        if self.cb_predicate is not None:
            callback_required = self.cb_predicate(csi_cluster.get_completion(), csi_cluster.get_age())
        else:
            callback_required = csi_cluster.get_completion_all()

        if callback_required:
            self.cb(csi_cluster)
            return True

        return False

class Pool(object):
    """
        A Pool is a collection of ESPARGOS boards.
    """
    def __init__(self, boards, ota_cache_timeout=5):
        self.logger = logging.getLogger("pyespargos.pool")
        self.boards = boards

        self.ota_cache_timeout = ota_cache_timeout

        # We have two caches: One for calibration packets, the other one for over-the-air packets
        self.cluster_cache_calib = OrderedDict()
        self.cluster_cache_ota = OrderedDict()

        self.input_list = list()
        self.input_cond = threading.Condition()

        for board_num, board in enumerate(self.boards):
            board.add_consumer(self.input_list, self.input_cond, board_num)

        self.callbacks = []
        self.logger.info(f"Created new pool with {len(boards)} board(s)")

        self.stored_calibration = None
        self.stats = dict()

    def set_calib(self, calibrate):
        for board in self.boards:
            board.set_calib(calibrate)

    def start(self):
        for board in self.boards:
            board.start()

    def stop(self):
        for board in self.boards:
            board.stop()

    def add_csi_callback(self, cb, cb_predicate = None):
        """
        Register callback function that is invoked whenever a new CSI cluster is completed.

        :param cb: The function to call, gets instance of class :class:`.ClusteredCSI` as parameter
        :param cb_predicate: A function with signature :code:`(csi_completion_state, csi_age)` that defines the conditions under which
            clustered CSI is regarded as completed and thus provided to the callback.
            :code:`csi_completion_state` is a tensor of shape :code:`(boardcount, constants.ROWS_PER_BOARD, constants.ANTENNAS_PER_ROW)`,
            and :code:`csi_age` is the age of the packet (relative to when any sensor first received it) in seconds
            If :code:`cb_predicate` returns true, clusterd CSI is regarded as completed.
            If no predicate is provided, the default behavior is to trigger the callback when CSI has been received
            from all sensors on all boards. If :code:`calibrated` is true (default), callback is provided CSI that is already phase-calibrated.
        """
        self.callbacks.append(CSICallback(cb, cb_predicate))

    def calibrate(self, per_board = True, duration = 2, exithandler = None, cable_lengths = None, cable_velocity_factors = None):
        # Clear calibration cache
        self.cluster_cache_calib.clear()

        # Enable calibration mode
        self.logger.info("Starting calibration")
        self.set_calib(True)

        # Run calibration for specified duration
        start = time.time()
        while (time.time() - start < duration) and (exithandler is None or exithandler.running):
            self.run()

        # Disable calibration mode
        self.logger.info("Finished calibration")
        self.set_calib(False)

        channel_primary = None
        channel_secondary = None

        # Collect calibration packets and compute calibration phases
        if per_board:
            phase_calibrations = []
            timestamp_calibrations = []

            for board_num, board in enumerate(self.boards):
                complete_clusters = []
                timestamp_offsets = []

                any_csi_count = 0
                for cluster in self.cluster_cache_calib.values():
                    if channel_primary is None:
                        channel_primary = cluster.get_primary_channel()
                        channel_secondary = cluster.get_secondary_channel()
                    else:
                        assert(channel_primary == cluster.get_primary_channel())
                        assert(channel_secondary == cluster.get_secondary_channel())

                    completion = cluster.get_completion()[board_num]
                    if np.any(completion):
                        any_csi_count = any_csi_count + 1

                    if np.all(completion):
                        complete_clusters.append(cluster.deserialize_csi_ht40()[board_num])
                        timestamp_offsets.append(cluster.get_sensor_timestamps()[board_num] - cluster.get_host_timestamp())

                self.logger.info(f"Board {board.get_name()}: Collected {any_csi_count} calibration clusters, out of which {len(complete_clusters)} are complete")
                if len(complete_clusters) == 0:
                    raise Exception("ESPARGOS calibration failed, did not receive phase reference signal")
                phase_calibrations.append(util.csi_interp_iterative(np.asarray(complete_clusters)))
                timestamp_calibrations.append(np.mean(np.asarray(timestamp_offsets), axis = 0))

            self.stored_calibration = CSICalibration(channel_primary, channel_secondary, np.asarray(phase_calibrations), np.asarray(timestamp_calibrations))

        else:
            complete_clusters = []
            timestamp_offsets = []

            for cluster in self.cluster_cache_calib.values():
                if channel_primary is None:
                    channel_primary = cluster.get_primary_channel()
                    channel_secondary = cluster.get_secondary_channel()
                else:
                    assert(channel_primary == cluster.get_primary_channel())
                    assert(channel_secondary == cluster.get_secondary_channel())

                completion = cluster.get_completion()
                if np.all(completion):
                    complete_clusters.append(cluster.deserialize_csi_ht40())
                    timestamp_offsets.append(cluster.get_sensor_timestamps() - cluster.get_host_timestamp())

            self.logger.info(f"Pool: Collected {len(self.cluster_cache_calib)} calibration clusters, out of which {len(complete_clusters)} are complete")
            phase_calibration = util.csi_interp_iterative(np.asarray(complete_clusters))
            time_calibration = np.mean(np.asarray(timestamp_offsets), axis = 0)

            self.stored_calibration = CSICalibration(channel_primary, channel_secondary, phase_calibration, time_calibration, board_cable_lengths=cable_lengths, board_cable_vfs=cable_velocity_factors)

    def get_calibration(self):
        return self.stored_calibration

    def handle_packets(self, packets):
        self.stats["packet_backlog"] = len(packets)

        # Deserialize CSI of all packets
        csi_bufs_int8 = np.zeros((len(packets), ctypes.sizeof(csi.csi_buf_t)), dtype = np.int8)
        for i, pkt in enumerate(packets):
            esp_num, serialized_csi, board_num = pkt[0], pkt[1], pkt[2]
            csi_bufs_int8[i] = serialized_csi.buf

        # The ESP32 provides CSI as int8_t values in (im, re) paris (in this order!)
        # To go from the (re, im) interpretation to (im, re), compute conjugate and multiply by 1.0j.
        csi_bufs_complex = csi_bufs_int8.astype(np.float32).view(np.complex64)
        csi_bufs_complex = -1.0j * np.conj(csi_bufs_complex)

        for pkt, csi_cplx in zip(packets, csi_bufs_complex):
            esp_num, serialized_csi, board_num = pkt[0], pkt[1], pkt[2]

            source_mac_str = binascii.hexlify(bytearray(serialized_csi.source_mac)).decode("utf-8")
            dest_mac_str = binascii.hexlify(bytearray(serialized_csi.dest_mac)).decode("utf-8")

            cluster_cache = self.cluster_cache_calib if serialized_csi.is_calib else self.cluster_cache_ota

            # Prepare a cache entry for a new cluster with a different identifier (here: MAC address & sequence control number)
            cluster_id = f"{source_mac_str}-{dest_mac_str}-{serialized_csi.seq_ctrl.seg:03x}-{serialized_csi.seq_ctrl.frag:01x}"
            if cluster_id not in cluster_cache:
                cluster_cache[cluster_id] = ClusteredCSI(source_mac_str, dest_mac_str, serialized_csi.seq_ctrl, len(self.boards))

            # Add received data for the antenna to the current cluster
            cluster_cache[cluster_id].add_csi(board_num, esp_num, serialized_csi, csi_cplx)

            if not serialized_csi.is_calib:
                # Check cluster cache for packets where callback is due and for stale packets
                stale = set()
                for id in cluster_cache.keys():
                    all_callbacks_fired = True
                    for cb in self.callbacks:
                        all_callbacks_fired = all_callbacks_fired and cb.try_call(cluster_cache[id])

                    if all_callbacks_fired:
                        stale.add(id)

                for id in cluster_cache.keys():
                    if cluster_cache[id].get_age() > self.ota_cache_timeout:
                        stale.add(id)

                for id in stale:
                    del cluster_cache[id]

    def get_shape(self):
        return (len(self.boards), constants.ROWS_PER_BOARD, constants.ANTENNAS_PER_ROW)

    def get_stats(self):
        return self.stats

    def run(self):
        with self.input_cond:
            self.input_cond.wait(timeout = 0.5)
            packets = [p for p in self.input_list]
            self.input_list.clear()

        self.handle_packets(packets)
