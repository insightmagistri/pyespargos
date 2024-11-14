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
	title: "Perceived TDOAs over Time"

	// Tab20 color cycle reordered: https://github.com/matplotlib/matplotlib/blob/main/lib/matplotlib/_cm.py#L1293
	property var colorCycle: ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94", "#f7b6d2", "#c7c7c7", "#dbdb8d", "#9edae5"]
	property color textColor: "#DDDDDD"

	Rectangle {
		anchors.fill: parent
		anchors.margins: 10
		color: "#202020"
		opacity: 1

		ColumnLayout {
			anchors.fill: parent
			Layout.alignment: Qt.AlignCenter

			Text {
				Layout.alignment: Qt.AlignCenter

				text: "Time Difference of Arrival over Time"
				color: "#ffffff"
				font.pixelSize: Math.max(22, window.width / 60)
				horizontalAlignment: Qt.AlignCenter

				Layout.margins: 10
			}

			ChartView {
				Layout.alignment: Qt.AlignCenter

				id: tdoasOverTime
				legend.visible: false
				Layout.fillWidth: true
				Layout.fillHeight: true
				Layout.margins: 10

				antialiasing: true
				backgroundColor: "#202020"

				property var newDataBacklog: Array()

				axes: [
					ValueAxis {
						id: tdoasOverTimeXAxis

						min: 0
						max: 20
						titleText: "<font color=\"#e0e0e0\">Mean RX Time [s]</font>"
						titleFont.bold: false
						gridLineColor: "#c0c0c0"
						tickInterval: 5
						tickType: ValueAxis.TicksDynamic
						labelsColor: "#e0e0e0"
					},
					ValueAxis {
						id: tdoasOverTimeYAxis

						min: -50
						max: 50
						titleText: "<font color=\"#e0e0e0\">Time of Arrival Difference [ns]</font>"
						titleFont.bold: false
						gridLineColor: "#c0c0c0"
						tickInterval: 5
						tickType: ValueAxis.TicksDynamic
						labelsColor: "#e0e0e0"
					}
				]

				Component.onCompleted : {
						let antennas = backend.sensorCount

						for (let ant = 0; ant < antennas; ++ant) {
							let phaseSeries = tdoasOverTime.createSeries(ChartView.SeriesTypeLine, "tx-" + ant, tdoasOverTimeXAxis, tdoasOverTimeYAxis)
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
						for (const elem of tdoasOverTime.newDataBacklog) {
							for (let ant = 0; ant < tdoasOverTime.count; ++ant)
								tdoasOverTime.series(ant).append(elem.time, elem.tdoas[ant]);

							tdoasOverTimeXAxis.max = elem.time
							tdoasOverTimeXAxis.min = elem.time - backend.maxCSIAge
						}

						tdoasOverTime.newDataBacklog = []
					}
				}

				Timer {
					interval: 1 * 1000
					running: true
					repeat: true
					onTriggered: {
						// Count and delete series points which are too old
						for (let ant = 0; ant < tdoasOverTime.count; ++ant) {
							let s = tdoasOverTime.series(ant);
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

					function onUpdateTDOAs(time, tdoas) {
						tdoasOverTime.newDataBacklog.push({
							"time" : time,
							"tdoas" : tdoas
						})
					}
				}
			}
		}
	}
}