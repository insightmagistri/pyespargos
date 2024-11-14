#!/usr/bin/env python3

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).absolute().parents[2]))

import numpy as np
import espargos
import argparse

import PyQt6.QtWidgets
import PyQt6.QtCharts
import PyQt6.QtCore
import PyQt6.QtQml

class EspargosDemoInstantaneousCSI(PyQt6.QtWidgets.QApplication):
	def __init__(self, argv):
		super().__init__(argv)

		# Parse command line arguments
		parser = argparse.ArgumentParser(description = "ESPARGOS Demo: Show instantaneous CSI over subcarrier index (single board)")
		parser.add_argument("hosts", type = str, help = "Comma-separated list of host addresses (IP or hostname) of ESPARGOS controllers")
		parser.add_argument("-b", "--backlog", type = int, default = 20, help = "Number of CSI datapoints to average over in backlog")
		parser.add_argument("-t", "--timedomain", default = False, help = "Display CSI in time-domain", action = "store_true")
		parser.add_argument("-s", "--shift-peak", default = False, help = "Time-shift CSI so that first peaks align", action = "store_true")
		self.args = parser.parse_args()

		# Set up ESPARGOS pool and backlog
		hosts = self.args.hosts.split(",")
		self.pool = espargos.Pool([espargos.Board(host) for host in hosts])
		self.pool.start()
		self.pool.calibrate(duration = 2, per_board=False)
		self.backlog = espargos.CSIBacklog(self.pool, size = self.args.backlog)
		self.backlog.start()

		# Qt setup
		self.aboutToQuit.connect(self.onAboutToQuit)
		self.engine = PyQt6.QtQml.QQmlApplicationEngine()
		self.sensor_count = self.backlog.get_ht40().shape[1] * self.backlog.get_ht40().shape[2] * self.backlog.get_ht40().shape[3]
		self.subcarrier_count = self.backlog.get_ht40().shape[4]
		self.subcarrier_range = np.arange(-self.subcarrier_count // 2, self.subcarrier_count // 2)

	@PyQt6.QtCore.pyqtProperty(int, constant=True)
	def sensorCount(self):
		return np.prod(self.pool.get_shape())

	@PyQt6.QtCore.pyqtProperty(list, constant=True)
	def subcarrierRange(self):
		return self.subcarrier_range.tolist()

	def exec(self):
		context = self.engine.rootContext()
		context.setContextProperty("backend", self)

		qmlFile = pathlib.Path(__file__).resolve().parent / "instantaneous-csi-ui.qml"
		self.engine.load(qmlFile.as_uri())
		if not self.engine.rootObjects():
			return -1

		return super().exec()

	# list parameters contain PyQt6.QtCharts.QLineSeries
	@PyQt6.QtCore.pyqtSlot(list, list, PyQt6.QtCharts.QValueAxis)
	def updateCSI(self, powerSeries, phaseSeries, axis):
		csi_backlog_ht40 = self.backlog.get_ht40()
		csi_ht40_shifted = espargos.util.shift_to_firstpeak(csi_backlog_ht40) if self.args.shift_peak else csi_backlog_ht40

		# TODO: If using per-board calibration, interpolation should also be per-board
		csi_interp_ht40 = espargos.util.csi_interp_iterative(csi_ht40_shifted, iterations = 5)
		csi_flat = np.reshape(csi_interp_ht40, (-1, csi_interp_ht40.shape[-1]))

		# Fill "gap" in subcarriers with interpolated data
		espargos.util.interpolate_ht40_gap(csi_flat)

		if self.args.timedomain:
			csi_flat = np.fft.fftshift(np.fft.ifft(np.fft.fftshift(csi_flat, axes = -1), axis = -1), axes = -1)
			csi_power = np.abs(csi_flat)
			axis.setMin(0)
			axis.setMax(csi_flat.shape[-1] / np.sqrt(2))
			csi_phase = np.angle(csi_flat * np.exp(-1.0j * np.angle(csi_flat[0, len(csi_flat[0]) // 2])))
		else:
			csi_power = 20 * np.log10(np.abs(csi_flat) + 0.00001)
			axis.setMin(10)
			axis.setMax(45)
			csi_phase = np.angle(csi_flat * np.exp(-1.0j * np.angle(csi_flat[0, csi_flat.shape[1] // 2])))

		#axis.setMax(max(np.max(csi_power), axis.max()))

		for pwr_series, phase_series, ant_pwr, ant_phase in zip(powerSeries, phaseSeries, csi_power, csi_phase):
			pwr_series.replace([PyQt6.QtCore.QPointF(s, p) for s, p in zip(self.subcarrier_range, ant_pwr)])
			phase_series.replace([PyQt6.QtCore.QPointF(s, p) for s, p in zip(self.subcarrier_range, ant_phase)])

	def onAboutToQuit(self):
		self.pool.stop()
		self.backlog.stop()
		self.engine.deleteLater()

	@PyQt6.QtCore.pyqtProperty(bool, constant=True)
	def timeDomain(self):
		return self.args.timedomain

app = EspargosDemoInstantaneousCSI(sys.argv)
sys.exit(app.exec())