import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtCharts

ApplicationWindow {
	id: window
	visible: true
	minimumWidth: 800
	minimumHeight: 500

	color: "#11191e"
	title: "Received Phases over Time"

	// Tab20 color cycle reordered: https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/_cm.py#L1293
	property var colorCycle: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5"]
	property color textColor: "#DDDDDD"

	Rectangle {
		anchors.fill: parent
		anchors.margins: 10
		color: "#151f26"
		opacity: 1

		ColumnLayout {
			anchors.fill: parent
			Layout.alignment: Qt.AlignCenter

			Text {
				Layout.alignment: Qt.AlignCenter

				text: "Received Phases over Time"
				color: "#ffffff"
				font.pixelSize: Math.max(22, window.width / 60)
				horizontalAlignment: Qt.AlignCenter

				Layout.margins: 10
			}

			ChartView {
				Layout.alignment: Qt.AlignCenter

				id: calibrationPhasesOverTime
				legend.visible: false
				Layout.fillWidth: true
				Layout.fillHeight: true
				Layout.margins: 10

				antialiasing: true
				backgroundColor: "#11191e"

				property var newDataBacklog: Array()

				axes: [
					ValueAxis {
						id: calibrationPhasesOverTimeXAxis

						min: 0
						max: 20
						titleText: "<font color=\"#e0e0e0\">Time [s]</font>"
						titleFont.bold: false
						gridLineColor: "#c0c0c0"
						tickInterval: 5
						tickType: ValueAxis.TicksDynamic
						labelsColor: "#e0e0e0"
					},
					ValueAxis {
						id: calibrationPhasesOverTimeYAxis

						min: -Math.PI
						max: Math.PI
						titleText: "<font color=\"#e0e0e0\">Phase Difference [rad]</font>"
						titleFont.bold: false
						gridLineColor: "#c0c0c0"
						tickInterval: 1
						tickType: ValueAxis.TicksDynamic
						labelsColor: "#e0e0e0"
					}
				]

				Component.onCompleted : {
						for (let ant = 0; ant < backend.sensorCount; ++ant) {
							let phaseSeries = calibrationPhasesOverTime.createSeries(ChartView.SeriesTypeLine, "tx-" + ant, calibrationPhasesOverTimeXAxis, calibrationPhasesOverTimeYAxis)
							phaseSeries.pointsVisible = false
							phaseSeries.color = colorCycle[ant % colorCycle.length]
							phaseSeries.useOpenGL = true
						}
				}

				Timer {
					interval: 1 / 40 * 1000
					running: true
					repeat: true
					onTriggered: {
						for (const elem of calibrationPhasesOverTime.newDataBacklog) {
							for (let ant = 0; ant < calibrationPhasesOverTime.count; ++ant)
								calibrationPhasesOverTime.series(ant).append(elem.time, elem.phases[ant]);

							calibrationPhasesOverTimeXAxis.max = elem.time
							calibrationPhasesOverTimeXAxis.min = elem.time - backend.maxCSIAge
						}

						calibrationPhasesOverTime.newDataBacklog = []
					}
				}

				Timer {
					interval: 1 * 1000
					running: true
					repeat: true
					onTriggered: {
						// Count and delete series points which are too old
						for (let ant = 0; ant < calibrationPhasesOverTime.count; ++ant) {
							let s = calibrationPhasesOverTime.series(ant);
							if (s.count > 2) {
								let toRemoveCount = 0;
								let now = s.at(s.count - 1).x;
								for (; toRemoveCount < s.count; ++toRemoveCount) {
									if (now - s.at(toRemoveCount).x < backend.maxCSIAge)
										break;
								}
								s.removePoints(0, toRemoveCount);
							}
						}
					}
				}

				Connections {
					target: backend

					function onUpdatePhases(time, phases) {
						calibrationPhasesOverTime.newDataBacklog.push({
							"time" : time,
							"phases" : phases
						})
					}
				}
			}
		}
	}
}