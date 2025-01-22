import QtQuick
import QtMultimedia

Item {
	CaptureSession {
		id: captureSession
		camera: WebCam
		videoOutput: videoOutput
	}

	VideoOutput {
		id: videoOutput
		anchors.fill: parent
	}

	ShaderEffect {
		id: spatialSpectrumShader
		width: videoOutput.contentRect.width
		height: videoOutput.contentRect.height
		anchors.verticalCenter: videoOutput.verticalCenter

		mesh: GridMesh {
        	resolution: Qt.size(180, 90)
    	}
		vertexShader: "spatialspectrum_vert.qsb"

		property variant source: ShaderEffectSource { sourceItem: videoOutput; sourceRect: videoOutput.contentRect; hideSource: true }

		property matrix4x4 horizontalSpatialSpectrum0
		property matrix4x4 horizontalSpatialSpectrum1
		property matrix4x4 horizontalSpatialSpectrum2
		property matrix4x4 horizontalSpatialSpectrum3
		property matrix4x4 horizontalSpatialSpectrum4
		property matrix4x4 horizontalSpatialSpectrum5
		property matrix4x4 horizontalSpatialSpectrum6
		property matrix4x4 horizontalSpatialSpectrum7

		property matrix4x4 verticalSpatialSpectrum0
		property matrix4x4 verticalSpatialSpectrum1
		property matrix4x4 verticalSpatialSpectrum2
		property matrix4x4 verticalSpatialSpectrum3
		property matrix4x4 verticalSpatialSpectrum4
		property matrix4x4 verticalSpatialSpectrum5
		property matrix4x4 verticalSpatialSpectrum6
		property matrix4x4 verticalSpatialSpectrum7

		fragmentShader: "spatialspectrum.qsb"

		Timer {
			interval: 50
			running: true
			repeat: true
			onTriggered: {
				backend.updateSpatialSpectrum()

				const verticalSpectrum = backend.verticalSpectrum
				const horizontalSpectrum = backend.horizontalSpectrum

				spatialSpectrumShader.verticalSpatialSpectrum0 = Qt.matrix4x4(verticalSpectrum.slice(  0,  16))
				spatialSpectrumShader.verticalSpatialSpectrum1 = Qt.matrix4x4(verticalSpectrum.slice( 16,  32))
				spatialSpectrumShader.verticalSpatialSpectrum2 = Qt.matrix4x4(verticalSpectrum.slice( 32,  48))
				spatialSpectrumShader.verticalSpatialSpectrum3 = Qt.matrix4x4(verticalSpectrum.slice( 48,  64))
				spatialSpectrumShader.verticalSpatialSpectrum4 = Qt.matrix4x4(verticalSpectrum.slice( 64,  80))
				spatialSpectrumShader.verticalSpatialSpectrum5 = Qt.matrix4x4(verticalSpectrum.slice( 80,  96))
				spatialSpectrumShader.verticalSpatialSpectrum6 = Qt.matrix4x4(verticalSpectrum.slice( 96, 112))
				spatialSpectrumShader.verticalSpatialSpectrum7 = Qt.matrix4x4(verticalSpectrum.slice(112, 128))

				spatialSpectrumShader.horizontalSpatialSpectrum0 = Qt.matrix4x4(horizontalSpectrum.slice(  0,  16))
				spatialSpectrumShader.horizontalSpatialSpectrum1 = Qt.matrix4x4(horizontalSpectrum.slice( 16,  32))
				spatialSpectrumShader.horizontalSpatialSpectrum2 = Qt.matrix4x4(horizontalSpectrum.slice( 32,  48))
				spatialSpectrumShader.horizontalSpatialSpectrum3 = Qt.matrix4x4(horizontalSpectrum.slice( 48,  64))
				spatialSpectrumShader.horizontalSpatialSpectrum4 = Qt.matrix4x4(horizontalSpectrum.slice( 64,  80))
				spatialSpectrumShader.horizontalSpatialSpectrum5 = Qt.matrix4x4(horizontalSpectrum.slice( 80,  96))
				spatialSpectrumShader.horizontalSpatialSpectrum6 = Qt.matrix4x4(horizontalSpectrum.slice( 96, 112))
				spatialSpectrumShader.horizontalSpatialSpectrum7 = Qt.matrix4x4(horizontalSpectrum.slice(112, 128))
			}
		}
	}

	Logo {
		source: "espargos_logo.svg"
		anchors.bottom: spatialSpectrumShader.bottom
	}
}
