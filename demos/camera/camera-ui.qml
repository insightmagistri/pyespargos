import "."

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCharts

ApplicationWindow {
	id: window
	visible: true
	minimumWidth: 800
	minimumHeight: 500

	color: "#333333"
	title: "ESPARGOS Camera Overlay Demo"

	footer: Pane {
		RowLayout {
			visible: WebCam.hasVideoInput
			anchors.fill: parent

			Text {
				text: WebCam.description + ' [Live]'
			}

			Text {
				text: WebCam.resolution.width + 'x' + WebCam.resolution.height
				Layout.alignment: Qt.AlignRight
			}
		}
	}

    // Full screen management
	visibility: ApplicationWindow.FullScreen
	Shortcut {
		sequence: "F11"
		onActivated: {
			if (window.visibility == ApplicationWindow.Windowed)
				window.visibility = ApplicationWindow.FullScreen
			else
				window.visibility = ApplicationWindow.Windowed
		}
	}

	Shortcut {
		sequence: "Esc"
		onActivated: window.close()
	}

	ColumnLayout {
		height: parent.height
		width: parent.width

		Text {
			Layout.alignment: Qt.AlignCenter
			font.pixelSize: Math.max(24, window.width / 70)
			text: "MUSIC Azimuth Spatial Spectrum"
			color: "#ffffff"
			Layout.margins: 10
		}

		CameraOverlay {
			Layout.fillWidth: true
			Layout.fillHeight: true
		}
	}
}