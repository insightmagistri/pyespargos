#!/usr/bin/env python3

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).absolute().parents[2]))

import videocamera
import numpy as np
import espargos
import argparse

import PyQt6.QtMultimedia
import PyQt6.QtWidgets
import PyQt6.QtCharts
import PyQt6.QtCore
import PyQt6.QtQml

class EspargosDemoCamera(PyQt6.QtWidgets.QApplication):
	def __init__(self, argv):
		super().__init__(argv)

		# Parse command line arguments
		parser = argparse.ArgumentParser(description = "ESPARGOS Demo: Overlay received power on top of camera image")
		parser.add_argument("host", type = str, help = "Host address (IP or hostname) of ESPARGOS controller")
		parser.add_argument("-b", "--backlog", type = int, default = 20, help = "Number of CSI datapoints to average over in backlog")
		parser.add_argument("-c", "--camera-index", type = int, help = "Index of the camera, if multiple cameras are available")
		self.args = parser.parse_args()

		# Set up ESPARGOS pool and backlog
		self.pool = espargos.Pool([espargos.Board(self.args.host)])
		self.pool.start()
		self.pool.calibrate(duration = 2)
		self.backlog = espargos.CSIBacklog(self.pool, size = self.args.backlog)
		self.backlog.start()

		# Qt setup
		self.aboutToQuit.connect(self.onAboutToQuit)
		self.engine = PyQt6.QtQml.QQmlApplicationEngine()

		# Camera setup
		self.videocamera = videocamera.VideoCamera(self.args.camera_index)

		# ESPARGOS is a UPA with half-wavelength antenna separation
		self.scanning_angles = np.linspace(np.deg2rad(-90), np.deg2rad(90), 128)
		self.k = np.pi * np.sin(self.scanning_angles)
		self.spatial_spectra_db = dict()

	def exec(self):
		context = self.engine.rootContext()
		context.setContextProperty("backend", self)
		context.setContextProperty("WebCam", self.videocamera)

		qmlFile = pathlib.Path(__file__).resolve().parent / "camera-ui.qml"
		self.engine.load(qmlFile.as_uri())
		if not self.engine.rootObjects():
			return -1

		# disable auto-focus and enable camera stream
		self.videocamera.setFocusMode(PyQt6.QtMultimedia.QCamera.FocusMode.FocusModeManual)
		self.videocamera.start()

		return super().exec()

	@PyQt6.QtCore.pyqtSlot()
	def updateSpatialSpectrum(self):
		csi_backlog_ht40 = self.backlog.get_ht40()

		# Compute array covariance matrix R over all backlog datapoints, all rows and all subcarriers
		R_h = np.einsum("dbris,dbrjs->ij", csi_backlog_ht40, np.conj(csi_backlog_ht40))
		R_v = np.einsum("dbics,dbjcs->ij", csi_backlog_ht40, np.conj(csi_backlog_ht40))
		self.spatial_spectra_db["horizontal"] = self.music(R_h)
		self.spatial_spectra_db["vertical"] = self.music(R_v)

	def music(self, R):
		steering_vectors = np.exp(1.0j * np.outer(self.k, np.arange(R.shape[0])))

		# Compute spatial spectrum using MUSIC algorithm based on R
		eig_val, eig_vec = np.linalg.eig(R)
		order = np.argsort(eig_val)[::-1]
		Qn = eig_vec[:,order][:,1:]
		spatial_spectrum = 1 / np.linalg.norm(np.einsum("ae,ra->er", np.conj(Qn), steering_vectors), axis = 0)
		spatial_spectrum /= 2

		return 20 * np.log10(spatial_spectrum)


	def onAboutToQuit(self):
		self.videocamera.stop()
		self.pool.stop()
		self.backlog.stop()
		self.engine.deleteLater()

	@PyQt6.QtCore.pyqtProperty(list, constant=True)
	def scanningAngles(self):
		return self.scanning_angles.tolist()
	
	@PyQt6.QtCore.pyqtProperty(list)
	def horizontalSpectrum(self):
		try:
			spectrum = self.spatial_spectra_db["horizontal"]
		except:
			spectrum = -np.inf * np.ones(self.scanning_angles.shape[0])
		return spectrum.tolist()

	@PyQt6.QtCore.pyqtProperty(list)
	def verticalSpectrum(self):
		try:
			spectrum = self.spatial_spectra_db["vertical"]
		except:
			spectrum = -np.inf * np.ones(self.scanning_angles.shape[0])
		return spectrum.tolist()


app = EspargosDemoCamera(sys.argv)
sys.exit(app.exec())
