#!/usr/bin/env python3

import numpy as np
from . import constants
from . import csi


def csi_interp_iterative(csi, weights=None, iterations=10):
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
	csi_interp = np.zeros((csi.shape[1], *csi.shape[2:]), dtype = csi.dtype)

	for b in range(csi.shape[1]):
		csi_interp[b] = csi_interp_iterative(csi[:,b], weights=weights, iterations=iterations)

	return csi_interp

def csi_interp_eigenvec(csi, weights=None):
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
	center_primary = constants.WIFI_CHANNEL1_FREQUENCY + constants.WIFI_CHANNEL_SPACING * (primary_channel - 1)
	center_secondary = constants.WIFI_CHANNEL1_FREQUENCY + constants.WIFI_CHANNEL_SPACING * (secondary_channel - 1)
	center_ht40 = (center_primary + center_secondary) / 2
	ht40_subcarrier_count = (csi.csi_buf_t.htltf_lower.size + csi.HT40_GAP_SUBCARRIERS * 2 + csi.csi_buf_t.htltf_higher.size) // 2
	assert(ht40_subcarrier_count % 2 == 1)
	return center_ht40 + np.arange(-ht40_subcarrier_count // 2, ht40_subcarrier_count // 2) * constants.WIFI_SUBCARRIER_SPACING

def get_calib_trace_wavelength(frequencies):
	return constants.SPEED_OF_LIGHT / (frequencies * np.sqrt(constants.CALIB_TRACE_EFFECTIVE_DIELECTRIC_CONSTANT))

def get_cable_wavelength(frequencies, velocity_factors):
	return constants.SPEED_OF_LIGHT / frequencies[np.newaxis, :] * velocity_factors[:, np.newaxis]

def interpolate_ht40_gap(csi_ht40):
	index_left = csi.csi_buf_t.htltf_lower.size // 2 - 1
	index_right = csi.csi_buf_t.htltf_lower.size // 2 + csi.HT40_GAP_SUBCARRIERS
	missing_indices = np.arange(index_left + 1, index_right)
	left = csi_ht40[..., index_left]
	right = csi_ht40[..., index_right]
	interp = (missing_indices - index_left) / (index_right - index_left)
	csi_ht40[..., missing_indices] = interp * right[..., np.newaxis] + (1 - interp) * left[..., np.newaxis]

def shift_to_firstpeak(csi_datapoints, max_delay_taps = 3, search_resolution = 40, peak_threshold = 0.4):
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
