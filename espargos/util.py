#!/usr/bin/env python3

import numpy as np
from . import constants
from . import csi


def csi_interp_iterative(csi, weights=None, iterations=10):
	"""
	Interpolates CSI data (frequency-domain or time-domain) using an iterative algorithm.
	Tries to sum up the CSI data phase-coherently with the least error.
	More details about the algorithm (which is quite straightforward) can be found in section
	"IV. Linear Interpolation Baseline" in the paper "GAN-based Massive MIMO Channel Model Trained on Measured Data".

	:param csi: The CSI data to interpolate. Complex-valued NumPy array. Can be an array with arbitrary dimensions, but the first dimension must be the number of CSI datapoints.
	:param weights: The weights to use for each CSI datapoint. If None, all datapoints are weighted equally.
	:param iterations: The number of iterations to perform. Default is 10.

	:return: The interpolated CSI data. Complex-valued NumPy array with the same shape as the input CSI data.
	"""
	if weights is None:
		weights = np.ones(len(csi), dtype = csi.dtype) / len(csi)

	phi = np.zeros_like(weights, dtype = csi.dtype)
	w = None
	
	for i in range(iterations):
		w = np.einsum("n,n,n...->...", weights, np.exp(-1.0j * phi), csi)
		phi = np.angle(np.einsum("a,na->n", np.conj(w.flatten()), csi.reshape(len(csi), -1)))
		#err = np.sum([weights[n] * np.linalg.norm(csi[n] - np.exp(1.0j * phi[n]) * w)**2 for n in range(len(csi))])

	return w

def csi_interp_iterative_by_array(csi, weights=None, iterations=10):
	"""
	Interpolates CSI data (frequency-domain or time-domain) using an iterative algorithm.
	Same as :func:`csi_interp_iterative`, but assumes that second dimension of :code:`csi` is the antenna array dimension and performs the interpolation for each antenna array separately.
	"""
	csi_interp = np.zeros((csi.shape[1], *csi.shape[2:]), dtype = csi.dtype)

	for b in range(csi.shape[1]):
		csi_interp[b] = csi_interp_iterative(csi[:,b], weights=weights, iterations=iterations)

	return csi_interp

def csi_interp_eigenvec(csi, weights=None):
	"""
	Interpolates CSI data (frequency-domain or time-domain) by finding the principal eigenvector of the covariance matrix.

	:param csi: The CSI data to interpolate. Complex-valued NumPy array. Can be an array with arbitrary dimensions, but the first dimension must be the number of CSI datapoints.
	:param weights: The weights to use for each CSI datapoint. If None, all datapoints are weighted equally.
	"""
	if weights is None:
		weights = np.ones(len(csi)) / len(csi)

	csi_shape = csi.shape[1:]
	csi = np.reshape(csi, (csi.shape[0], -1))
	R = np.einsum("n,na,nb->ab", weights, csi, np.conj(csi))

	# eig is faster than eigh for small matrices like the one here
	w, v = np.linalg.eig(R)
	principal = np.argmax(w)

	return np.reshape(v[:, principal], csi_shape)


def get_frequencies_ht40(primary_channel, secondary_channel):
	"""
	Returns the frequencies of the subcarriers in an HT40 2.4GHz WiFi channel.
	:param primary_channel: The primary channel number.
	:param secondary_channel: The secondary channel number.
	:return: The frequencies of the subcarriers, in Hz, NumPy array.
	"""
	center_primary = constants.WIFI_CHANNEL1_FREQUENCY + constants.WIFI_CHANNEL_SPACING * (primary_channel - 1)
	center_secondary = constants.WIFI_CHANNEL1_FREQUENCY + constants.WIFI_CHANNEL_SPACING * (secondary_channel - 1)
	center_ht40 = (center_primary + center_secondary) / 2
	ht40_subcarrier_count = (csi.csi_buf_t.htltf_lower.size + csi.HT40_GAP_SUBCARRIERS * 2 + csi.csi_buf_t.htltf_higher.size) // 2
	assert(ht40_subcarrier_count % 2 == 1)
	return center_ht40 + np.arange(-ht40_subcarrier_count // 2, ht40_subcarrier_count // 2) * constants.WIFI_SUBCARRIER_SPACING

def get_calib_trace_wavelength(frequencies):
	"""
	Returns the wavelength of the subcarriers on the calibration traces on the ESPARGOS sensor board.

	:param frequencies: The frequencies of the subcarriers, in Hz, NumPy array.
	:return: The wavelengths of the subcarriers, in meters, NumPy array.
	"""
	return constants.CALIB_TRACE_GROUP_VELOCITY / frequencies

def get_cable_wavelength(frequencies, velocity_factors):
	"""
	Returns the wavelength of the provided subcarrier frequencies on a cable with the given velocity factors.

	:param frequencies: The frequencies of the subcarriers, in Hz, NumPy array.
	:param velocity_factors: The velocity factors of the cable, NumPy array.
	:return: The wavelengths of the subcarriers, in meters, NumPy array.
	"""
	return constants.SPEED_OF_LIGHT / frequencies[np.newaxis, :] * velocity_factors[:, np.newaxis]

def interpolate_ht40_gap(csi_ht40):
	"""
	Apply linear interpolation to determine realistic values for the subcarrier channel coefficients in the gap between the bonded channels in an HT40 channel.

	:param csi_ht40: The CSI data for an HT40 channel. Complex-valued NumPy array with arbitrary shape, but the last dimension must be the subcarriers.
	:return: The CSI data with the values in the gap filled in.
	"""
	index_left = csi.csi_buf_t.htltf_lower.size // 2 - 1
	index_right = csi.csi_buf_t.htltf_lower.size // 2 + csi.HT40_GAP_SUBCARRIERS
	missing_indices = np.arange(index_left + 1, index_right)
	left = csi_ht40[..., index_left]
	right = csi_ht40[..., index_right]
	interp = (missing_indices - index_left) / (index_right - index_left)
	csi_ht40[..., missing_indices] = interp * right[..., np.newaxis] + (1 - interp) * left[..., np.newaxis]

def shift_to_firstpeak(csi_datapoints, max_delay_taps = 3, search_resolution = 40, peak_threshold = 0.4):
	"""
	Shifts the CSI data so that the first peak of the channel impulse response is at time 0.
	Uses a simple but rather computation-efficient algorithm to find the first peak of the channel impulse response (as opposed to superresolution-based approach).

	:param csi_datapoints: The CSI data to shift, frequency-domain. Complex-valued NumPy array with shape (datapoints, arrays, rows, columns, subcarriers).
	:param max_delay_taps: The maximum number of time taps to shift the CSI data by.
	:param search_resolution: The number of search points (granularity) to use for the time shift.
	:param peak_threshold: The threshold for the peak detection, as a fraction of the maximum peak power.

	:return: The frequency-domain CSI data with the first peak of the channel impulse response at time 0.
	"""
	# Time-shift all collected CSI so that first "peak" is at time 0
	# CSI datapoints has shape (datapoints, arrays, rows, columns, subcarriers)
	shifts = np.linspace(-max_delay_taps, 0, search_resolution)
	subcarrier_range = np.arange(-csi_datapoints.shape[-1] // 2, csi_datapoints.shape[-1] // 2) + 1
	shift_vectors = np.exp(1.0j * np.outer(shifts, 2 * np.pi * subcarrier_range / csi_datapoints.shape[-1]))
	powers_by_delay = np.abs(np.einsum("lbrms,ds->lbrmd", csi_datapoints, shift_vectors))
	max_peaks = np.max(powers_by_delay, axis = -1)
	first_peak = np.argmax(powers_by_delay > peak_threshold * max_peaks[:,:,:,:,np.newaxis], axis = -1)
	shift_to_firstpeak = shift_vectors[first_peak]

	return shift_to_firstpeak * csi_datapoints
