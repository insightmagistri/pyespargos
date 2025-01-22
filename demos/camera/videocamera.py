from PyQt6.QtCore import pyqtProperty, QSize
from PyQt6.QtMultimedia import QMediaDevices, QCamera

class VideoCamera(QCamera):
	"QCamera which exposes relevant properties for QML."

	def __init__(self, cameraId = None):
		videoDevices = QMediaDevices.videoInputs()
		if cameraId is not None and cameraId < len(videoDevices):
			videoDevice = videoDevices[cameraId]
		else:
			videoDevice = QMediaDevices.defaultVideoInput()

		super().__init__(videoDevice)

		if not videoDevice.isNull():
			availableFormats = videoDevice.videoFormats()
			fmt = availableFormats[-1] # last is best here: JPEG 1920x1080
			self.setCameraFormat(fmt)

	@pyqtProperty(str, constant=True)
	def description(self) -> str:
		return self.cameraDevice().description()

	@pyqtProperty(QSize, constant=True)
	def resolution(self) -> QSize:
		return self.cameraFormat().resolution()

	@pyqtProperty(bool, constant=True)
	def hasVideoInput(self) -> bool:
		return self.isAvailable()
