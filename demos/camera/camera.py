#!/usr/bin/env python3

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).absolute().parents[2]))

import matplotlib.colors
import espargos.constants
import videocamera
import numpy as np
import espargos
import argparse

import PyQt6.QtMultimedia
import PyQt6.QtWidgets
import PyQt6.QtCharts
import PyQt6.QtCore
import PyQt6.QtQml

import matplotlib.pyplot as plt

class EspargosDemoCamera(PyQt6.QtWidgets.QApplication):
	beamspacePowerImagedataChanged = PyQt6.QtCore.pyqtSignal(list)

	def __init__(self, argv):
		super().__init__(argv)

		# Parse command line arguments
		parser = argparse.ArgumentParser(description = "ESPARGOS Demo: Overlay received power on top of camera image")
		parser.add_argument("host", type = str, help = "Host address (IP or hostname) of ESPARGOS controller")
		parser.add_argument("-b", "--backlog", type = int, default = 20, help = "Number of CSI datapoints to average over in backlog")
		parser.add_argument("-c", "--camera-index", type = int, help = "Index of the camera, if multiple cameras are available")
		parser.add_argument("-d", "--colorize-delay", default = False, help = "Visualize delay of beamspace components using colors", action = "store_true")
		parser.add_argument("-i", "--no-interpolation", default = False, help = "Do not use datapoint interpolation to reduce computational complexity (can slightly improve appearance)", action = "store_true")
		parser.add_argument("-ra", "--resolution-azimuth", type = int, default = 32, help = "Beamspace resolution for azimuth angle")
		parser.add_argument("-re", "--resolution-elevation", type = int, default = 32, help = "Beamspace resolution for elevation angle")
		parser.add_argument("-md", "--max-delay", type = float, default = 0.2, help = "Maximum delay in samples for colorizing delay")
		display_group = parser.add_mutually_exclusive_group()
		display_group.add_argument("-f", "--beamspace-fft", default = False, help = "Approximate beamspace transform via FFT (faster, but inaccurate)", action = "store_true")
		display_group.add_argument("-m", "--music", default = False, help = "Display spatial spectrum computed via MUSIC algorithm", action = "store_true")
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

		# Pre-compute 2d steering vectors to avoid recomputation
		self.scanning_angles_azi = np.linspace(np.deg2rad(-60), np.deg2rad(60), self.args.resolution_azimuth)
		self.scanning_angles_ele = np.linspace(np.deg2rad(-60), np.deg2rad(60), self.args.resolution_elevation)
		self.k_c = -np.pi * np.cos(self.scanning_angles_ele)[np.newaxis,:] * np.sin(self.scanning_angles_azi)[:,np.newaxis]
		self.k_r = -np.pi * np.sin(self.scanning_angles_ele)

		# phase_c depends on both elevation and azimuth angle and has shape (columns, azimuth angle, elevation angle)
		# phase_r only depends on elevation angle and has shape (rows, elevation angle)
		# steering_vectors_2d has shape (rows, columns, azimuth angle, elevation angle)
		antenna_index_c = np.arange(espargos.constants.ANTENNAS_PER_ROW)
		antenna_index_r = np.arange(espargos.constants.ROWS_PER_BOARD)
		phase_c = antenna_index_c[:,np.newaxis,np.newaxis] * self.k_c[np.newaxis,:,:]
		phase_r = antenna_index_r[:,np.newaxis] * self.k_r[np.newaxis,:]

		self.steering_vectors_2d = np.exp(1.0j * (phase_c[np.newaxis,:,:,:] + phase_r[:,np.newaxis,np.newaxis,:]))

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

		espargos.util.interpolate_ht40_gap(csi_backlog_ht40)

		# Shift all CSI datapoints in time so that LoS component arrives at the same time
		csi_backlog_ht40 = espargos.util.shift_to_firstpeak_sync(csi_backlog_ht40)

		# For computational efficiency reasons, reduce number of datapoints to one by interpolating over all datapoints
		if not self.args.no_interpolation:
			csi_backlog_ht40 = np.asarray([espargos.util.csi_interp_iterative(csi_backlog_ht40, iterations = 5)])

		# Option 1: MUSIC spatial spectrum (simplest)
		if self.args.music:
			# Compute array covariance matrix R over all backlog datapoints, all rows and all subcarriers
			R_h = np.einsum("dbris,dbrjs->ij", csi_backlog_ht40, np.conj(csi_backlog_ht40))
			R_v = np.einsum("dbics,dbjcs->ij", csi_backlog_ht40, np.conj(csi_backlog_ht40))
			self.spatial_spectra_db["horizontal"] = self._music_algorithm(R_h)
			self.spatial_spectra_db["vertical"] = self._music_algorithm(R_v)

		else:
			# Option 2: Beamspace via FFT
			if self.args.beamspace_fft:
				# This is technically not the correct way to go from antenna domain to beamspace,
				# but it is approximately correct if azimuth *or* elevation angles are small
				# csi_zeropadded has shape (datapoints, azimuth / row, elevation / column, subcarriers)
				csi_zeropadded = np.zeros((csi_backlog_ht40.shape[0], self.args.resolution_azimuth, self.args.resolution_elevation, csi_backlog_ht40.shape[-1]), dtype = csi_backlog_ht40.dtype)
				real_rows_half = csi_backlog_ht40.shape[2] // 2
				real_cols_half = csi_backlog_ht40.shape[3] // 2
				zeropadded_rows_half = csi_zeropadded.shape[2] // 2
				zeropadded_cols_half = csi_zeropadded.shape[1] // 2
				csi_zeropadded[:,zeropadded_cols_half-real_cols_half:zeropadded_cols_half+real_cols_half,zeropadded_rows_half-real_rows_half:zeropadded_rows_half+real_rows_half,:] = np.swapaxes(csi_backlog_ht40[:,0,:,:,:], 1, 2)
				csi_zeropadded = np.fft.ifftshift(csi_zeropadded, axes = (1, 2))
				beam_frequency_space = np.fft.fft2(csi_zeropadded, axes = (1, 2))
				beam_frequency_space = np.fft.fftshift(beam_frequency_space, axes = (1, 2))
			
			# Option 3: Beamspace
			else:
				# Compute sum of received power per steering angle over all datapoints and subcarriers
				# real 2d spatial spectrum is too slow...
				# we can use 2D FFT to get to beamspace, which of course is technically not correct
				# (cannot separate 2D steering vector into Kronecker product of azimuth / elevation steering vectors)
				beam_frequency_space = np.einsum("rcae,dbrcs->daes", self.steering_vectors_2d, csi_backlog_ht40, optimize = True)

			squared_power_by_beam = np.sum(np.abs(beam_frequency_space)**2, axis=(0, 3))**2
			color_value = (squared_power_by_beam - np.min(squared_power_by_beam)) / (np.max(squared_power_by_beam) - np.min(squared_power_by_beam) + 1e-6)

			if self.args.colorize_delay:
				# Compute beam powers and delay. Beam power is value, delay is hue.
				mean_delay_by_beam = np.angle(np.sum(beam_frequency_space[...,1:] * np.conj(beam_frequency_space[...,:-1]), axis=(0, 3)))

				hsv = np.zeros((beam_frequency_space.shape[1], beam_frequency_space.shape[2], 3))
				hsv[:,:,0] = np.clip((mean_delay_by_beam - (-0.1)) / self.args.max_delay, 0, 1)
				hsv[:,:,1] = 0.8
				hsv[:,:,2] = color_value

				wifi_image_rgb = matplotlib.colors.hsv_to_rgb(hsv)
				alpha_channel = np.ones((*wifi_image_rgb.shape[:2], 1))
				wifi_image_rgba = np.clip(np.concatenate((wifi_image_rgb, alpha_channel), axis=-1), 0, 1)
				self.beamspace_power_imagedata = np.asarray(np.swapaxes(wifi_image_rgba, 0, 1).flatten() * 255, dtype = np.uint8)
			else:
				self.beamspace_power = np.sum(np.abs(beam_frequency_space)**2, axis = (0, 3))
				self.beamspace_power_imagedata = np.zeros(4 * self.beamspace_power.size, dtype = np.uint8)
				self.beamspace_power_imagedata[1::4] = np.clip(np.swapaxes(color_value, 0, 1).flatten(), 0, 1) * 255
				self.beamspace_power_imagedata[3::4] = 255

			self.beamspacePowerImagedataChanged.emit(self.beamspace_power_imagedata.tolist())

	def _music_algorithm(self, R):
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
	
	@PyQt6.QtCore.pyqtProperty(bool, constant=True)
	def music(self):
		return self.args.music


	@PyQt6.QtCore.pyqtProperty(int, constant=True)
	def resolutionAzimuth(self):
		return self.args.resolution_azimuth

	@PyQt6.QtCore.pyqtProperty(int, constant=True)
	def resolutionElevation(self):
		return self.args.resolution_elevation

app = EspargosDemoCamera(sys.argv)
sys.exit(app.exec())
