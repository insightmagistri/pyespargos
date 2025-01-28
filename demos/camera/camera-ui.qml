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

    // Full screen management
	visibility: ApplicationWindow.Windowed
	Shortcut {
		sequence: "F11"
		onActivated: {
			if (window.visibility == ApplicationWindow.Windowed) {
				window.visibility = ApplicationWindow.FullScreen
				footer.visible = false
			} else {
				window.visibility = ApplicationWindow.Windowed
				footer.visible = true
			}
		}
	}

	Shortcut {
		sequence: "Esc"
		onActivated: window.close()
	}


	CameraOverlay {
		anchors.fill: parent
	}

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
}