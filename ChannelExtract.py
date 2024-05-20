import math
import sys
import os
import json
import numpy as np
import h5py
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QDoubleSpinBox,
    QFileDialog,
    QHeaderView,
)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.widgets import LassoSelector
from matplotlib.path import Path
import matplotlib.image as mpimg
import subprocess
import shutil
import signal
import psutil


class ScatterPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        fig = Figure()
        self.canvas = FigureCanvas(fig)
        layout.addWidget(self.canvas)

        self.ax = fig.add_subplot(111)

        self.x = np.arange(1, 65)
        self.y = np.arange(1, 65)
        self.x, self.y = np.meshgrid(self.x, self.y)
        self.x = self.x.flatten()
        self.y = self.y.flatten()

        self.ax.scatter(self.x, self.y, c="k", s=5)

        self.lasso = LassoSelector(
            self.ax,
            self.lasso_callback,
            button=[1, 3],
            useblit=True,
        )

        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.ax.invert_yaxis()  # Invert the y-axis

        self.canvas.draw()

    def lasso_callback(self, verts):
        path = Path(verts)
        new_selected_points = [
            (x, y) for x, y in zip(self.x, self.y) if path.contains_point((x, y))
        ]

        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.ShiftModifier:
            if hasattr(self, "selected_points"):
                self.selected_points.extend(new_selected_points)
            else:
                self.selected_points = new_selected_points
        else:
            self.selected_points = new_selected_points

        if hasattr(self, "selected_points_plot"):
            self.selected_points_plot.remove()

        self.selected_points_plot = self.ax.scatter(
            [point[0] for point in self.selected_points],
            [point[1] for point in self.selected_points],
            c="red",
            s=5,
        )

        verts = np.append(verts, [verts[0]], axis=0)
        if hasattr(self, "lasso_line"):
            self.lasso_line.remove()

        self.lasso_line = self.ax.plot(
            verts[:, 0], verts[:, 1], "b-", linewidth=2, alpha=0.5
        )[0]

        self.canvas.draw()

        print("Selected points:")
        for point in self.selected_points:
            print(point)

    def onrelease(self, event):
        if self.lasso.active:
            self.lasso_line.set_visible(False)
            self.canvas.draw()


class ChannelExtract(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Channel Selection Toolbox")
        self.setGeometry(100, 100, 1600, 900)
        # Create main widget and layout
        self.centralWidget = QWidget(self)
        self.setCentralWidget(self.centralWidget)
        self.mainLayout = QVBoxLayout()
        self.centralWidget.setLayout(self.mainLayout)

        # Create header
        self.headerLabel = QLabel("Channel Selection Toolbox")
        self.headerLabel.setAlignment(Qt.AlignCenter)
        self.headerLabel.setStyleSheet(
            "background-color: #ADD8E6; color: #000080; font-size: 20px; padding: 10px;"
        )
        self.mainLayout.addWidget(self.headerLabel)

        # Create input file path layout
        inputLayout = QHBoxLayout()
        uploadButton = QPushButton("Upload .brw Files")
        uploadButton.setStyleSheet(
            "background-color: #ADD8E6; color: #000080; font-size: 16px; padding: 5px;"
        )
        uploadButton.clicked.connect(self.uploadFiles)
        inputLayout.addWidget(uploadButton)
        self.mainLayout.addLayout(inputLayout)

        # Create data table
        self.dataTable = QTableWidget()
        self.dataTable.setColumnCount(10)
        self.dataTable.setHorizontalHeaderLabels(
            [
                "File Path",
                "File Name",
                "Version",
                "Data Format",
                "Active Channels",
                "Data per Channel",
                "Recording Time (Seconds)",
                "Sampling (Hz)",
                "Status",
                "Select",
            ]
        )
        self.dataTable.horizontalHeader().setStyleSheet("font-size: 16px;")
        self.dataTable.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.mainLayout.addWidget(self.dataTable)

        # Create file name label
        self.fileNameLabel = QLabel("Analysis File: ")
        self.fileNameLabel.setAlignment(Qt.AlignCenter)
        self.fileNameLabel.setStyleSheet(
            "background-color: #87CEEB; color: #000080; font-size: 16px; padding: 5px;"
        )
        self.mainLayout.addWidget(self.fileNameLabel)

        # Create separator
        self.mainLayout.addSpacing(10)

        # Create channel selection layout
        channelLayout = QHBoxLayout()

        # Create input grid
        self.inputGridLabel = QLabel("Select Channels for Export")
        self.inputGridLabel.setAlignment(Qt.AlignCenter)
        self.inputGridLabel.setStyleSheet("font-size: 18px;")
        self.inputGridWidget = ScatterPlot()

        inputGridLayout = QVBoxLayout()
        inputGridLayout.addWidget(self.inputGridLabel)
        inputGridLayout.addWidget(self.inputGridWidget)
        channelLayout.addLayout(inputGridLayout, stretch=3)  # Increased stretch factor

        # Create channel selection layout
        channelLayout = QHBoxLayout()

        # Create input grid
        self.inputGridLabel = QLabel("Select Channels for Export")
        self.inputGridLabel.setAlignment(Qt.AlignCenter)
        self.inputGridLabel.setStyleSheet("font-size: 18px;")
        self.inputGridWidget = ScatterPlot()
        self.inputGridWidget.setMinimumSize(
            800, 800
        )  # Set minimum size for the input grid

        inputGridLayout = QVBoxLayout()
        inputGridLayout.addWidget(self.inputGridLabel)
        inputGridLayout.addWidget(self.inputGridWidget)
        channelLayout.addLayout(inputGridLayout)

        # Create channel count and settings layout
        settingsLayout = QVBoxLayout()

        self.channelCountLabel = QLabel("Channel Count")
        self.channelCountLabel.setAlignment(Qt.AlignCenter)
        self.channelCountLabel.setStyleSheet("font-size: 16px;")
        self.channelCountValue = QLabel("0")
        self.channelCountValue.setAlignment(Qt.AlignCenter)
        self.channelCountValue.setStyleSheet("font-size: 20px; font-weight: bold;")

        rowSkipLabel = QLabel("# Rows to Skip:")
        self.rowSkipSpinBox = QSpinBox()
        self.rowSkipSpinBox.setRange(0, 3)

        colSkipLabel = QLabel("# Columns to Skip:")
        self.colSkipSpinBox = QSpinBox()
        self.colSkipSpinBox.setRange(0, 3)

        downsampleLabel = QLabel("Downsampling (Hz):")
        self.downsampleSpinBox = QDoubleSpinBox()
        self.downsampleSpinBox.setRange(0, 20000)
        self.downsampleSpinBox.setValue(100)

        startTimeLabel = QLabel("Start Time (s):")
        self.startTimeSpinBox = QDoubleSpinBox()
        self.startTimeSpinBox.setRange(0, 50)

        endTimeLabel = QLabel("End Time (s):")
        self.endTimeSpinBox = QDoubleSpinBox()

        exportButton = QPushButton("Export Channels")
        exportButton.setStyleSheet(
            "background-color: #ADD8E6; color: #000080; font-size: 16px; padding: 5px;"
        )
        exportButton.clicked.connect(self.exportChannels)

        settingsLayout.addWidget(self.channelCountLabel)
        settingsLayout.addWidget(self.channelCountValue)
        settingsLayout.addWidget(rowSkipLabel)
        settingsLayout.addWidget(self.rowSkipSpinBox)
        settingsLayout.addWidget(colSkipLabel)
        settingsLayout.addWidget(self.colSkipSpinBox)
        settingsLayout.addWidget(downsampleLabel)
        settingsLayout.addWidget(self.downsampleSpinBox)
        settingsLayout.addWidget(startTimeLabel)
        settingsLayout.addWidget(self.startTimeSpinBox)
        settingsLayout.addWidget(endTimeLabel)
        settingsLayout.addWidget(self.endTimeSpinBox)
        settingsLayout.addWidget(exportButton)

        settingsWidget = QWidget()
        settingsWidget.setLayout(settingsLayout)
        settingsWidget.setFixedWidth(200)  # Adjust the width as needed

        channelLayout.addWidget(settingsWidget, alignment=Qt.AlignCenter)

        # Create output grid
        self.outputGridLabel = QLabel("Channels Exported")
        self.outputGridLabel.setAlignment(Qt.AlignCenter)
        self.outputGridLabel.setStyleSheet("font-size: 18px;")
        self.outputGridWidget = ScatterPlot()
        self.outputGridWidget.setMinimumSize(800, 800)

        outputGridLayout = QVBoxLayout()
        outputGridLayout.addWidget(self.outputGridLabel)
        outputGridLayout.addWidget(self.outputGridWidget)
        channelLayout.addLayout(outputGridLayout)

        self.mainLayout.addLayout(channelLayout)

        # Initialize variables
        self.inputFileName = ""
        self.uploadedImage = None
        self.typ = None
        self.size = [0, 65, 65, 0]
        self.dataTable.status_items = {}
        self.dataTable.select_buttons = {}

        self.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = min(self.width() // 3, self.height() // 2)
        self.inputGridWidget.setFixedSize(size, size)
        self.outputGridWidget.setFixedSize(size, size)

    def uploadFiles(self):
        options = QFileDialog.Options()
        fileNames, _ = QFileDialog.getOpenFileNames(
            self, "Open .brw Files", "", "BRW Files (*.brw)", options=options
        )
        if fileNames:
            tableData = []
            self.imageDict = {}  # Create a dictionary to store images
            for fileName in fileNames:
                h5 = h5py.File(fileName, "r")
                self.get_type(h5)
                parameters = self.parameter(h5)
                chsList = parameters["recElectrodeList"]
                filePath = os.path.dirname(fileName)
                baseName = os.path.basename(fileName)

                brwFileName = os.path.basename(fileName)
                dateSlice = "_".join(brwFileName.split("_")[:4])
                dateSliceNumber = (
                    dateSlice.split("slice")[0]
                    + "slice"
                    + dateSlice.split("slice")[1][:1]
                )
                imageName = f"{dateSliceNumber}_pic_cropped.jpg"
                imageFolder = os.path.dirname(fileName)
                imagePath = os.path.join(imageFolder, imageName)

                if os.path.exists(imagePath):
                    image = mpimg.imread(imagePath)
                else:
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Information)
                    msg.setText(f"No image found, manually select image for {baseName}")
                    msg.setWindowTitle("Image Not Found")
                    msg.exec_()

                    imageFileName, _ = QFileDialog.getOpenFileName(
                        self,
                        "Upload Slice Image",
                        "",
                        "Image Files (*.jpg *.png)",
                        options=options,
                    )
                    if imageFileName:
                        image = mpimg.imread(imageFileName)
                    else:
                        image = None

                self.imageDict[fileName] = (
                    image  # Store the image in the dictionary using the file name as the key
                )

                tableData.append(
                    [
                        filePath,
                        baseName,
                        parameters["Ver"],
                        parameters["Typ"],
                        len(chsList),
                        parameters["nRecFrames"],
                        round(parameters["nRecFrames"] / parameters["samplingRate"]),
                        parameters["samplingRate"],
                        "Not Started",
                        QPushButton("Select"),
                    ]
                )
                h5.close()
            self.populateTable(tableData)

    def get_type(self, h5):
        if "ExperimentSettings" in h5.keys():
            self.typ = "bw5"
        elif "/3BRecInfo/3BRecVars/NRecFrames" in h5.keys():
            self.typ = "bw4"
        else:
            self.typ = "File Not Recognized"

    def updateGrid(self):
        # Update input grid based on uploaded image and selected file
        if self.inputFileName and os.path.exists(self.inputFileName):
            h5 = h5py.File(self.inputFileName, "r")
            self.get_type(h5)
            parameters = self.parameter(h5)
            chsList = parameters["recElectrodeList"]
            Frames = parameters["nRecFrames"]
            endTime = parameters["recordingLength"]

            Xs, Ys, idx = self.getChMap(chsList)

            # Update the input grid scatter plot
            self.inputGridWidget.ax.clear()
            if self.uploadedImage is not None:
                self.inputGridWidget.ax.imshow(
                    self.uploadedImage, extent=self.size, aspect="auto"
                )
            self.inputGridWidget.ax.scatter(Xs, Ys, c="k", s=5)

            self.inputGridWidget.ax.set_xlim(self.size[0], self.size[1])
            self.inputGridWidget.ax.set_ylim(self.size[2], self.size[3])
            self.inputGridWidget.ax.set_xticks([])
            self.inputGridWidget.ax.set_yticks([])

            self.inputGridWidget.ax.invert_yaxis()  # Invert the y-axis
            self.inputGridWidget.canvas.draw()

            self.endTimeSpinBox.setRange(0, endTime)
            self.endTimeSpinBox.setValue(endTime)

            h5.close()
        else:
            self.fileNameLabel.setText("No .brw file selected")

            # Clear the input grid scatter plot
            self.inputGridWidget.ax.clear()
            self.inputGridWidget.canvas.draw()

    def updateOutputGrid(self, selectedPoints):
        if selectedPoints:
            chX = []
            chY = []
            for point in selectedPoints:
                x, y = point
                if (
                    y % (self.rowSkipSpinBox.value() + 1) == 0
                    and x % (self.colSkipSpinBox.value() + 1) == 0
                ):
                    chX.append(x)
                    chY.append(y)

            h5 = h5py.File(self.inputFileName, "r")
            parameters = self.parameter(h5)
            chsList = parameters["recElectrodeList"]
            xs, ys, idx = self.getChMap(chsList)
            h5.close()

            # Update the output grid scatter plot
            self.outputGridWidget.ax.clear()
            if self.uploadedImage is not None:
                self.outputGridWidget.ax.imshow(
                    self.uploadedImage, extent=self.size, aspect="auto"
                )
            self.outputGridWidget.ax.scatter(xs, ys, c="grey", s=5, alpha=0.1)
            self.outputGridWidget.ax.scatter(chX, chY, c="green", s=5)
            self.outputGridWidget.ax.set_xlim(self.size[0], self.size[1])
            self.outputGridWidget.ax.set_ylim(self.size[2], self.size[3])
            self.outputGridWidget.ax.set_xticks([])
            self.outputGridWidget.ax.set_yticks([])
            self.outputGridWidget.ax.invert_yaxis()  # Invert the y-axis
            self.outputGridWidget.canvas.draw()
        else:
            # Clear the output grid scatter plot
            self.outputGridWidget.ax.clear()
            self.outputGridWidget.canvas.draw()

    def populateTable(self, data):
        self.dataTable.setRowCount(len(data))
        for i, row in enumerate(data):
            for j, item in enumerate(row[:-2]):
                table_item = QTableWidgetItem(str(item))
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                table_item.setTextAlignment(Qt.AlignCenter)
                self.dataTable.setItem(i, j, table_item)

            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setBackground(QColor("red"))
            self.dataTable.setItem(i, len(row) - 2, status_item)

            select_button = QPushButton("Select")
            select_button.clicked.connect(lambda _, row=i: self.selectFile(row))
            self.dataTable.setCellWidget(i, len(row) - 1, select_button)

            # Store the status item and select button for later use
            self.dataTable.status_items[i] = status_item
            self.dataTable.select_buttons[i] = select_button

    def selectFile(self, row):
        fileName = os.path.join(
            self.dataTable.item(row, 0).text(), self.dataTable.item(row, 1).text()
        )
        self.inputFileName = fileName
        self.uploadedImage = self.imageDict.get(
            fileName
        )  # Retrieve the image from the dictionary using the file name as the key
        self.updateGrid()

        # Check if there was a previously selected row
        previously_selected_row = self.dataTable.currentRow()
        if previously_selected_row >= 0 and previously_selected_row != row:
            # Update the status and enable the select button for the previously selected row
            previous_status_item = self.dataTable.status_items[previously_selected_row]
            if previous_status_item.background() != QColor("green"):
                previous_status_item.setBackground(QColor("red"))

            previous_select_button = self.dataTable.cellWidget(
                previously_selected_row, self.dataTable.columnCount() - 1
            )
            if previous_select_button is not None:
                previous_select_button.setEnabled(True)
                previous_select_button.setText("Select")

        status_item = self.dataTable.status_items[row]
        status_item.setBackground(QColor("yellow"))

        select_button = self.dataTable.select_buttons[row]
        select_button.setEnabled(False)

        # Clear the output grid
        self.outputGridWidget.ax.clear()
        self.outputGridWidget.canvas.draw()

        self.dataTable.selectRow(row)

    def parameter(self, h5):
        if self.typ == "bw4":
            parameters = {}
            parameters["Ver"] = "BW4"

            parameters["nRecFrames"] = h5["/3BRecInfo/3BRecVars/NRecFrames"][0]
            parameters["samplingRate"] = h5["/3BRecInfo/3BRecVars/SamplingRate"][0]
            parameters["recordingLength"] = (
                parameters["nRecFrames"] / parameters["samplingRate"]
            )
            parameters["signalInversion"] = h5["/3BRecInfo/3BRecVars/SignalInversion"][
                0
            ]  # depending on the acq version it can be 1 or -1
            # in uVolt
            parameters["maxUVolt"] = h5["/3BRecInfo/3BRecVars/MaxVolt"][0]
            # in uVolt
            parameters["minUVolt"] = h5["/3BRecInfo/3BRecVars/MinVolt"][0]
            parameters["bitDepth"] = h5["/3BRecInfo/3BRecVars/BitDepth"][
                0
            ]  # number of used bit of the 2 byte coding
            parameters["qLevel"] = (
                2 ^ parameters["bitDepth"]
            )  # quantized levels corresponds to 2^num of bit to encode the signal
            parameters["fromQLevelToUVolt"] = (
                parameters["maxUVolt"] - parameters["minUVolt"]
            ) / parameters["qLevel"]
            try:
                parameters["recElectrodeList"] = h5["/3BRecInfo/3BMeaStreams/Raw/Chs"][
                    :
                ]  # list of the recorded channels
                parameters["Typ"] = "RAW"
            except:
                parameters["recElectrodeList"] = h5[
                    "/3BRecInfo/3BMeaStreams/WaveletCoefficients/Chs"
                ][:]
                parameters["Typ"] = "WAV"
            parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])

        else:
            if "Raw" in h5["Well_A1"].keys():
                json_s = json.loads(h5["ExperimentSettings"][0].decode("utf8"))
                parameters = {}
                parameters["Ver"] = "BW5"
                parameters["Typ"] = "RAW"
                parameters["nRecFrames"] = h5["Well_A1/Raw"].shape[0] // 4096
                parameters["samplingRate"] = json_s["TimeConverter"]["FrameRate"]
                parameters["recordingLength"] = (
                    parameters["nRecFrames"] / parameters["samplingRate"]
                )
                parameters["signalInversion"] = int(
                    1
                )  # depending on the acq version it can be 1 or -1
                parameters["maxUVolt"] = int(4125)  # in uVolt
                parameters["minUVolt"] = int(-4125)  # in uVolt
                # number of used bit of the 2 byte coding
                parameters["bitDepth"] = int(12)
                parameters["qLevel"] = (
                    2 ^ parameters["bitDepth"]
                )  # quantized levels corresponds to 2^num of bit to encode the signal
                parameters["fromQLevelToUVolt"] = (
                    parameters["maxUVolt"] - parameters["minUVolt"]
                ) / parameters["qLevel"]
                parameters["recElectrodeList"] = self.getChMap()[
                    :
                ]  # list of the recorded channels
                parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])
            else:
                json_s = json.loads(h5["ExperimentSettings"][0].decode("utf8"))
                parameters = {}
                parameters["Ver"] = "BW5"
                parameters["Typ"] = "WAV"

                samplingRate = h5.attrs["SamplingRate"]
                nChannels = len(h5["Well_A1/StoredChIdxs"])
                coefsTotalLength = len(h5["Well_A1/WaveletBasedEncodedRaw"])
                compressionLevel = h5["Well_A1/WaveletBasedEncodedRaw"].attrs[
                    "CompressionLevel"
                ]
                framesChunkLength = h5["Well_A1/WaveletBasedEncodedRaw"].attrs[
                    "DataChunkLength"
                ]
                coefsChunkLength = (
                    math.ceil(framesChunkLength / pow(2, compressionLevel)) * 2
                )
                numFrames = 0
                chIdx = 1
                coefsPosition = chIdx * coefsChunkLength
                while coefsPosition < coefsTotalLength:
                    length = int(coefsChunkLength / 2)
                    for i in range(compressionLevel):
                        length *= 2
                    numFrames += length
                    coefsPosition += coefsChunkLength * nChannels

                parameters["nRecFrames"] = numFrames
                parameters["recordingLength"] = numFrames / samplingRate

                parameters["samplingRate"] = json_s["TimeConverter"]["FrameRate"]
                parameters["signalInversion"] = int(
                    1
                )  # depending on the acq version it can be 1 or -1
                parameters["maxUVolt"] = int(4125)  # in uVolt
                parameters["minUVolt"] = int(-4125)  # in uVolt
                # number of used bit of the 2 byte coding
                parameters["bitDepth"] = int(12)
                parameters["qLevel"] = (
                    2 ^ parameters["bitDepth"]
                )  # quantized levels corresponds to 2^num of bit to encode the signal
                parameters["fromQLevelToUVolt"] = (
                    parameters["maxUVolt"] - parameters["minUVolt"]
                ) / parameters["qLevel"]
                parameters["recElectrodeList"] = self.getChMap()[
                    :
                ]  # list of the recorded channels
                parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])

        return parameters

    def getChMap(self, chsList=None):
        # Get channel map coordinates
        newChs = np.zeros(4096, dtype=[("Row", "<i2"), ("Col", "<i2")])
        for idx in range(4096):
            column = (idx // 64) + 1
            row = idx % 64 + 1
            if row == 0:
                row = 64
            if column == 0:
                column = 1
            newChs[idx] = (np.int16(row), np.int16(column))

        if chsList is None:
            return newChs[np.lexsort((newChs["Col"], newChs["Row"]))]
        else:
            Ys = []
            Xs = []
            idx = []
            for n, item in enumerate(chsList):
                Ys.append(item["Col"])
                Xs.append(item["Row"])
                idx.append(n)
            return Xs, Ys, idx

    def exportChannels(self):
        # Export selected channels to a new BRW file
        selectedPoints = self.inputGridWidget.selected_points
        if selectedPoints:
            chX = []
            chY = []
            for point in selectedPoints:
                x, y = point
                if (
                    y % (self.rowSkipSpinBox.value() + 1) == 0
                    and x % (self.colSkipSpinBox.value() + 1) == 0
                ):
                    chX.append(x)
                    chY.append(y)
            print("Selected Channels: ", len(chX))
            print("Opening file:")
            h5 = h5py.File(self.inputFileName, "r")
            parameters = self.parameter(h5)
            chsList = parameters["recElectrodeList"]
            xs, ys, idx = self.getChMap(chsList)
            h5.close()

            newChs = np.zeros(len(chX), dtype=[("Row", "<i2"), ("Col", "<i2")])
            for idx, (x, y) in enumerate(zip(chX, chY)):
                newChs[idx] = (np.int16(y), np.int16(x))

            newChs = newChs[np.lexsort((newChs["Col"], newChs["Row"]))]

            inputFilePath = os.path.dirname(self.inputFileName)
            inputFileName = os.path.basename(self.inputFileName)
            outputFileName = inputFileName.split(".")[0] + "_exportCh"
            outputFileNameBrw = outputFileName + ".brw"
            outputPath = os.path.join(inputFilePath, outputFileNameBrw)

            dset = self.writeCBrw(
                inputFilePath, outputFileName, inputFileName, parameters
            )
            dset.createNewBrw()
            dset.appendBrw(
                outputPath,
                parameters["nRecFrames"],
                newChs,
                parameters["samplingRate"],
                self.downsampleSpinBox.value(),
                self.startTimeSpinBox.value(),
                self.endTimeSpinBox.value(),
            )
            # Update the output grid with exported channels
            self.outputGridWidget.ax.clear()
            if self.uploadedImage is not None:
                self.outputGridWidget.ax.imshow(
                    self.uploadedImage, extent=self.size, aspect="auto"
                )
            self.outputGridWidget.ax.scatter(xs, ys, c="grey", s=5, alpha=0.1)
            self.outputGridWidget.ax.scatter(chX, chY, c="red", s=5)
            self.outputGridWidget.ax.set_xlim(self.size[0], self.size[1])
            self.outputGridWidget.ax.set_ylim(self.size[2], self.size[3])
            self.outputGridWidget.ax.set_xticks([])
            self.outputGridWidget.ax.set_yticks([])
            self.outputGridWidget.ax.invert_yaxis()
            self.outputGridWidget.canvas.draw()

            # Update the status light to green and change the select button to "Redo"
            selected_row = self.dataTable.currentRow()
            if selected_row >= 0:
                status_item = self.dataTable.status_items[selected_row]
                status_item.setBackground(QColor("green"))

                select_button = self.dataTable.cellWidget(
                    selected_row, self.dataTable.columnCount() - 1
                )
                if select_button is not None:
                    select_button.setEnabled(True)
                    select_button.setText("Redo")

    def writeCBrw(self, path, name, template, parameters):
        # Create and write to a new BRW file
        dset = writeCBrw(path, name, template, parameters)
        return dset


class writeCBrw:
    def __init__(self, path, name, template, parameters):
        self.path = path
        self.fileName = name
        self.template = template
        self.description = parameters["Ver"]
        self.version = parameters["Typ"]
        self.brw = h5py.File(os.path.join(self.path, self.template), "r")
        self.samplingrate = parameters["samplingRate"]
        self.frames = parameters["nRecFrames"]
        self.signalInversion = parameters["signalInversion"]
        self.maxVolt = parameters["maxUVolt"]
        self.minVolt = parameters["minUVolt"]
        self.bitdepth = parameters["bitDepth"]
        self.chs = parameters["recElectrodeList"]
        self.QLevel = np.power(2, parameters["bitDepth"])
        self.fromQLevelToUVolt = (self.maxVolt - self.minVolt) / self.QLevel

    def createNewBrw(self):
        newName = os.path.join(self.path, self.fileName + ".brw")
        new = h5py.File(newName, "w")
        new.attrs.__setitem__("Description", self.description)
        new.attrs.__setitem__("Version", self.version)
        new.create_dataset("/3BRecInfo/3BRecVars/SamplingRate", data=[np.float64(100)])
        new.create_dataset(
            "/3BRecInfo/3BRecVars/NewSampling", data=[np.float64(self.samplingrate)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/NRecFrames", data=[np.float64(self.frames)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/SignalInversion",
            data=[np.float64(self.signalInversion)],
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/MaxVolt", data=[np.float64(self.maxVolt)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/MinVolt", data=[np.float64(self.minVolt)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/BitDepth", data=[np.float64(self.bitdepth)]
        )
        new.create_dataset("/3BRecInfo/3BMeaStreams/Raw/Chs", data=[self.chs])
        new.create_dataset("/3BRecInfo/3BRecVars/Ver", data=[self.description])
        new.create_dataset("/3BRecInfo/3BRecVars/Typ", data=[self.version])
        self.newDataset = new
        self.newDataset.close()

    def appendBrw(self, fName, frames, chs, fs, NewSampling, ss, st):
        brwAppend = h5py.File(fName, "a")
        del brwAppend["/3BRecInfo/3BRecVars/NewSampling"]
        try:
            del brwAppend["/3BRecInfo/3BMeaStreams/Raw/Chs"]
        except:
            del brwAppend["/3BRecInfo/3BMeaStreams/WaveletCoefficients/Chs"]
        del brwAppend["/3BRecInfo/3BRecVars/NRecFrames"]
        del brwAppend["/3BRecInfo/3BRecVars/SamplingRate"]
        brwAppend.create_dataset("/3BRecInfo/3BMeaStreams/Raw/Chs", data=chs)
        brwAppend.create_dataset(
            "/3BRecInfo/3BRecVars/NRecFrames", data=[np.int64(frames)]
        )
        brwAppend.create_dataset(
            "/3BRecInfo/3BRecVars/SamplingRate", data=[np.float64(fs)]
        )
        brwAppend.create_dataset(
            "/3BRecInfo/3BRecVars/NewSampling", data=[np.float64(NewSampling)]
        )
        brwAppend.create_dataset(
            "/3BRecInfo/3BRecVars/startTime", data=[np.float64(ss)]
        )
        brwAppend.create_dataset("/3BRecInfo/3BRecVars/endTime", data=[np.float64(st)])
        brwAppend.close()

    def close(self):
        self.newDataset.close()
        self.brw.close()


class LoadingScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Loading")
        self.setFixedSize(300, 100)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.label = QLabel("Checking for updates...")
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_label(self, text):
        self.label.setText(text)


def force_quit_application(app_name):
    try:
        # Iterate over all running processes
        for proc in psutil.process_iter():
            try:
                # Check if the process name matches the application name
                if proc.name() == app_name:
                    # Terminate the process
                    if os.name == "nt":  # Windows
                        proc.terminate()
                    else:  # macOS and Linux
                        proc.send_signal(signal.SIGTERM)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception as e:
        print(f"Error occurred while trying to force quit {app_name}: {str(e)}")


def run_commands_in_terminal(commands):
    try:
        if sys.platform == "darwin":  # macOS
            script = "#!/bin/bash\n"
            script += "\n".join(commands)
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'tell application "Terminal" to do script "{script}"',
                ]
            )
        elif sys.platform == "win32":  # Windows
            script = " & ".join(commands)
            subprocess.Popen(["start", "cmd", "/k", script], shell=True)
        else:  # Linux or other Unix-like systems
            script = "\n".join(commands)
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", script])
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running commands: {str(e)}")
    except Exception as e:
        print(f"Error occurred: {str(e)}")


def check_for_updates():
    repo_url = "https://github.com/booka66/ChannelExtract.git"
    home_dir = os.path.expanduser("~")
    local_path = os.path.join(home_dir, "ChannelExtract")
    loading_screen = LoadingScreen()

    try:
        try:
            subprocess.check_output(["git", "--version"])
        except subprocess.CalledProcessError:
            raise Exception("Git is not installed")

        # Fetch the latest commit hash from the remote repository using git command
        remote_commit = (
            subprocess.check_output(["git", "ls-remote", repo_url, "HEAD"])
            .decode("utf-8")
            .split()[0]
        )

        # Check if the repository exists locally
        if os.path.exists(local_path):
            # Get the current commit hash of the local repository
            local_commit = (
                subprocess.check_output(["git", "-C", local_path, "rev-parse", "HEAD"])
                .decode("utf-8")
                .strip()
            )
        else:
            local_commit = ""

        # Compare the commit hashes
        if remote_commit != local_commit:
            # Prompt the user to update or automatically initiate the update process
            reply = QMessageBox.question(
                None,
                "Update Available",
                "A new version is available. Do you want to update?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                loading_screen.show()
                loading_screen.update_label("Updating...")
                loading_screen.update_progress(25)

                # Remove the existing repository if it exists
                if os.path.exists(local_path):
                    shutil.rmtree(local_path)

                # Clone the latest version of the repository
                subprocess.call(["git", "clone", repo_url, local_path])

                loading_screen.update_label("Installing dependencies...")
                loading_screen.update_progress(40)

                print("Installing dependencies...")
                commands = [
                    "cd ~",
                    "cd ChannelExtract",
                    "pip install -r requirements.txt",
                    "pyinstaller --onefile --windowed ChannelExtract.py",
                ]
                run_commands_in_terminal(commands)
                loading_screen.update_label("Building executable...")
                loading_screen.update_progress(60)
                # os.chdir(local_path)
                # os.system("source venv/bin/activate")
                # os.system("pip install -r requirements.txt")
                #
                # loading_screen.update_label("Building executable...")
                # loading_screen.update_progress(60)
                #
                # print("Building executable...")
                # os.system(
                #     f"pyinstaller --onefile --windowed {local_path}/ChannelExtract.py"
                # )
                # print("Checking if executable was built...")
                # if os.path.exists(os.path.join(local_path, "dist", "ChannelExtract")):
                #     print("Executable built successfully")
                #
                #     # Determine the application directory based on the operating system
                #     if sys.platform == "darwin":
                #         app_dir = "/Applications"
                #     elif sys.platform == "win32":
                #         app_dir = os.path.join(
                #             os.environ["PROGRAMFILES"], "ChannelExtract"
                #         )
                #     else:
                #         raise Exception("Unsupported operating system")
                #
                #     # Remove the existing application in the Applications folder if it exists
                #     old_app_path = os.path.join(app_dir, "ChannelExtract.app")
                #     if os.path.exists(old_app_path):
                #         shutil.rmtree(old_app_path)
                #
                #     # Move the newly built application to the Applications folder
                #     new_app_path = os.path.join(
                #         local_path, "dist", "ChannelExtract.app"
                #     )
                #     shutil.move(new_app_path, app_dir)
                #     print("Application moved to the Applications folder")
                #
                #     # Force quit the old version of the application if it's running

                if sys.platform == "darwin":
                    app_dir = "/Applications"
                elif sys.platform == "win32":
                    app_dir = os.path.join(os.environ["PROGRAMFILES"], "ChannelExtract")
                else:
                    raise Exception("Unsupported operating system")

                loading_screen.update_label("Update complete")
                loading_screen.update_progress(100)
                force_quit_application("ChannelExtract")

                # Restart the application
                # subprocess.Popen(
                #     [
                #         os.path.join(
                #             app_dir,
                #             "ChannelExtract.app",
                #             "Contents",
                #             "MacOS",
                #             "ChannelExtract",
                #         )
                #     ]
                # )
                sys.exit()

    except subprocess.CalledProcessError as e:
        error_message = f"Error occurred during update check: {str(e)}"
        print(error_message)
        QMessageBox.critical(None, "Update Error", error_message)
    except Exception as e:
        error_message = f"Error occurred during update check: {str(e)}"
        print(error_message)
        QMessageBox.critical(None, "Update Error", error_message)
    finally:
        loading_screen.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChannelExtract()

    # Check for updates
    check_for_updates()

    sys.exit(app.exec_())
