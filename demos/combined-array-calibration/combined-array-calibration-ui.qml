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
	title: "Combined Array Calibration Demo"

    // Full screen management
	visibility: ApplicationWindow.Windowed
	Shortcut {
		sequence: "F11"
		onActivated: {
			window.visibility = window.visibility == ApplicationWindow.Windowed ? ApplicationWindow.FullScreen : ApplicationWindow.Windowed
		}
	}

	Shortcut {
		sequence: "Esc"
		onActivated: window.close()
	}

	// Tab20 color cycle reordered: https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/_cm.py#L1293
	property var colorCycle: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5"]

	ColumnLayout {
		height: parent.height
		width: parent.width

		Text {
			Layout.alignment: Qt.AlignCenter
			font.pixelSize: Math.max(24, window.width / 70)
			text: "Combined Array Calibration Demo"
			color: "#ffffff"
			Layout.margins: 10
		}

		ChartView {
			id: csiPhase
			Layout.alignment: Qt.AlignTop
			legend.visible: false
			legend.labelColor: "#e0e0e0"
			Layout.fillWidth: true
			Layout.fillHeight: true
			antialiasing: true
			backgroundColor: "#202020"
			dropShadowEnabled: true

			axes: [
				ValueAxis {
					id: csiPhaseSubcarrierAxis

					min: backend.subcarrierRange[0]
					max: backend.subcarrierRange.slice(-1)[0]
					titleText: "<font color=\"#e0e0e0\">Subcarrier Index</font>"
					titleFont.bold: false
					gridLineColor: "#c0c0c0"
					tickInterval: 20
					tickType: ValueAxis.TicksDynamic
					labelsColor: "#e0e0e0"
				},
				ValueAxis {
					id: csiPhaseAxis

					min: -3.14
					max: 3.14
					titleText: "<font color=\"#e0e0e0\">Phase [rad]</font>"
					titleFont.bold: false
					gridLineColor: "#c0c0c0"
					tickInterval: 2
					tickType: ValueAxis.TicksDynamic
					labelsColor: "#e0e0e0"
				}
			]

			Component.onCompleted : {
				for (let ant = 0; ant < backend.sensorCount; ++ant) {
					let series = csiPhase.createSeries(ChartView.SeriesTypeLine, "tx-" + ant, csiPhaseSubcarrierAxis, csiPhaseAxis);
					series.pointsVisible = false;
					const sensorIndexInBoard = ant % backend.sensorCountPerBoard;
					const boardIndex = ~~(ant / backend.sensorCountPerBoard);
					const colorIndex = (backend.colorBySensorIndex ? sensorIndexInBoard : boardIndex) % colorCycle.length;
					series.color = colorCycle[colorIndex];
					series.useOpenGL = true;

					for (const s of backend.subcarrierRange) {
						series.append(s, 0)
					}
				}
			}
		}
	}

	Timer {
		interval: 1 / 60 * 1000
		running: true
		repeat: true
		onTriggered: {
			let phaseSeries = [];
			for (let i = 0; i < backend.sensorCount; ++i)
				phaseSeries.push(csiPhase.series(i));

			backend.updateCalibrationResult(phaseSeries)
		}
	}
}