#!/usr/bin/env python3

import websockets.sync.client
import http.client
import threading
import logging
import ctypes
import json
from . import csi


class EspargosHTTPStatusError(Exception):
    "Raised when the ESPARGOS HTTP API returns an invalid status code"
    pass


class EspargosUnexpectedResponseError(Exception):
    "Raised when the server (ESPARGOS controller) provides unexpected response. Is the server really ESPARGOS?"
    pass


class Board(object):
    csistream_timeout = 5

    def __init__(self, host):
        self.logger = logging.getLogger("pyespargos.board")

        self.host = host
        try:
            identification = self.fetch("identify")
        except TimeoutError:
            self.logger.error(f"Could not connect to {self.host}")
            raise TimeoutError

        if identification != "ESPARGOS":
            raise EspargosUnexpectedResponseError

        self.netconf = json.loads(self.fetch("get_netconf"))
        self.ip_info = json.loads(self.fetch("get_ip_info"))
        self.wificonf = json.loads(self.fetch("get_wificonf"))

        self.logger.info(
            f"Identified ESPARGOS at {self.ip_info['ip']} as {self.get_name()}")

        self.csistream_connected = True
        self.consumers = []

    def get_name(self):
        return self.netconf["hostname"]

    def csistream_handle_message(self, message):
        pktsize = ctypes.sizeof(csi.csistream_pkt_t)
        assert(len(message) % pktsize == 0)
        for i in range(0, len(message), pktsize):
            packet = csi.csistream_pkt_t(message[i:i + pktsize])
            serialized_csi = csi.serialized_csi_t(packet.buf)

            if serialized_csi.type_header == csi.ESPARGOS_SPI_TYPE_HEADER_CSI:
                for clist, cv, args in self.consumers:
                    with cv:
                        clist.append((packet.esp_num, serialized_csi, *args))
                        cv.notify()

    def csistream_loop(self):
        with websockets.sync.client.connect("ws://" + self.host + "/csi", close_timeout = 0.5) as websocket:
            self.csistream_connected = True
            timeout_total = 0
            timeout_once = 0.2
            while self.csistream_connected:
                try:
                    message = websocket.recv(timeout_once)
                    timeout_total = 0
                    self.csistream_handle_message(message)
                except TimeoutError:
                    timeout_total = timeout_total + timeout_once

                if timeout_total > self.csistream_timeout:
                    self.logger.warn("Websockets timeout, disconnecting")
                    self.csistream_connected = False

    def start(self):
        self.csistream_thread = threading.Thread(target=self.csistream_loop)
        self.csistream_thread.start()
        self.logger.info(f"Started CSI stream for {self.get_name()}")

    def stop(self):
        if self.csistream_connected:
            self.csistream_connected = False
            self.csistream_thread.join()
            self.logger.info(f"Stopped CSI stream for {self.get_name()}")

    def set_calib(self, calibrate):
        res = self.fetch("set_calib", "1" if calibrate else "0")
        if res != "ok":
            self.logger.error(f"Invalid response: {res}")
            raise EspargosUnexpectedResponseError

    def add_consumer(self, clist, cv, *args):
        self.consumers.append((clist, cv, args))

    def fetch(self, path, data=None):
        method = "GET" if data is None else "POST"
        conn = http.client.HTTPConnection(self.host, timeout=5)
        conn.request(method, "/" + path, data)

        try:
            res = conn.getresponse()
        except TimeoutError:
            self.logger.error(f"Timeout in HTTP request for {self.host}/{path}")
            raise TimeoutError

        if res.status != 200:
            raise EspargosHTTPStatusError

        return res.read().decode("utf-8")