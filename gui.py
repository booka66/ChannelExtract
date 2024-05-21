# You must use Python 3.11
# Make sure to source the virtual environment before running the script:
# source ./matlab_env/bin/activate
#
# DO NOT RUN THIS:
# pyinstaller --additional-hooks-dir=hooks --paths /Users/booka66/research/matlab_env/lib/python3.11/site-packaes/matlab/enine main.py
import math
import os
import sys
import threading
import time
import zipfile
from subprocess import call
from time import perf_counter
from playsound import playsound
from pyqtgraph.Qt.QtCore import QRect
from tqdm import tqdm
import skvideo.io
import cv2
from mss import mss

import h5py
import matlab.engine
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QObject, QPoint, QRectF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from pyqtgraph.Qt.QtWidgets import QMessageBox, QTabWidget
from PyQt5.QtSvg import QSvgGenerator, QSvgRenderer

BACKGROUND = QColor("#4a4e69")
ACTIVE = QColor("#808080")

HOVER = QColor("#00ff00")
SELECTED = QColor("#008000")
PLOTTED = QColor("#a4161a")

SEIZURE = QColor("#0096c7")
SE = QColor("#ffb703")


class ColorCell(QLabel):
    clicked = pyqtSignal(int, int)

    def __init__(self, row, col, color):
        super().__init__()
        self.setAutoFillBackground(True)
        self.setColor(color)
        self.clicked_state = False
        self.plotted_state = False
        self.plotted_shape = None
        self.hover_color = HOVER
        self.selected_color = SELECTED
        self.plotted_color = PLOTTED
        self.hover_width = 2
        self.selected_width = 2
        self.plotted_width = 2
        self.row = row
        self.col = col

    def setColor(self, color, strength=1.0):
        strength = max(0, min(strength, 1))

        hsv_color = color.toHsv()

        hsv_color.setHsv(
            hsv_color.hue(), int(hsv_color.saturation() * strength), hsv_color.value()
        )

        rgb_color = QColor.fromHsv(
            hsv_color.hue(), hsv_color.saturation(), hsv_color.value()
        )

        opacity = self.palette().color(QPalette.Window).alphaF()
        rgb_color.setAlphaF(opacity)

        palette = self.palette()
        palette.setColor(QPalette.Window, rgb_color)
        self.setPalette(palette)

    def enterEvent(self, event):
        if not self.window().is_recording_video:
            if not self.clicked_state and self.underMouse():
                self.update()

    def leaveEvent(self, event):
        if not self.window().is_recording_video:
            if not self.clicked_state and not self.underMouse():
                self.update()

    def mousePressEvent(self, event):
        if not self.window().is_recording_video:
            if event.button() == Qt.LeftButton:
                self.clicked_state = not self.clicked_state
                self.clicked.emit(self.row, self.col)
                self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.window().is_recording_video:
            if self.underMouse() and not self.clicked_state:
                painter = QPainter(self)
                painter.setPen(QPen(self.hover_color, self.hover_width))
                painter.drawRect(
                    self.rect().adjusted(
                        self.hover_width // 2,
                        self.hover_width // 2,
                        -self.hover_width // 2,
                        -self.hover_width // 2,
                    )
                )
            elif self.clicked_state:
                painter = QPainter(self)
                painter.setPen(QPen(self.selected_color, self.selected_width))
                painter.drawRect(
                    self.rect().adjusted(
                        self.selected_width // 2,
                        self.selected_width // 2,
                        -self.selected_width // 2,
                        -self.selected_width // 2,
                    )
                )
            elif self.plotted_shape == "":
                painter = QPainter(self)
                painter.setPen(QPen(self.plotted_color, self.selected_width + 1))
                painter.drawEllipse(
                    self.rect().adjusted(
                        self.plotted_width // 2,
                        self.plotted_width // 2,
                        -self.plotted_width // 2,
                        -self.plotted_width // 2,
                    )
                )
            elif self.plotted_shape == "󰔷":
                painter = QPainter(self)
                painter.setPen(QPen(self.plotted_color, self.selected_width + 1))
                triangle_points = [
                    QPoint(
                        self.rect().center().x(),
                        self.rect().top() + self.plotted_width // 2,
                    ),
                    QPoint(
                        self.rect().left() + self.plotted_width // 2,
                        self.rect().bottom() - self.plotted_width // 2,
                    ),
                    QPoint(
                        self.rect().right() - self.plotted_width // 2,
                        self.rect().bottom() - self.plotted_width // 2,
                    ),
                ]
                painter.drawPolygon(triangle_points)
            elif self.plotted_shape == "x":
                painter = QPainter(self)
                painter.setPen(QPen(self.plotted_color, self.selected_width + 1))
                painter.drawLine(
                    self.rect().topLeft()
                    + QPoint(self.plotted_width // 2, self.plotted_width // 2),
                    self.rect().bottomRight()
                    - QPoint(self.plotted_width // 2, self.plotted_width // 2),
                )
                painter.drawLine(
                    self.rect().topRight()
                    - QPoint(self.plotted_width // 2, -self.plotted_width // 2),
                    self.rect().bottomLeft()
                    + QPoint(self.plotted_width // 2, -self.plotted_width // 2),
                )
            elif self.plotted_shape == "":
                painter = QPainter(self)
                painter.setPen(QPen(self.plotted_color, self.selected_width + 1))
                painter.drawRect(
                    self.rect().adjusted(
                        self.plotted_width // 2,
                        self.plotted_width // 2,
                        -self.plotted_width // 2,
                        -self.plotted_width // 2,
                    )
                )


class GridWidget(QWidget):
    cell_clicked = pyqtSignal(int, int)

    def __init__(self, rows, cols):
        super().__init__()
        self.rows = rows
        self.cols = cols
        self.grid = QGridLayout()
        self.grid.setSpacing(0)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignCenter)
        self.setLayout(self.grid)
        self.cells = []
        self.createGrid()
        self.selected_cell = None
        self.background_image = None

    def createGrid(self):
        self.cells = [[None for _ in range(self.cols)] for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                # Inactive cells are black
                cell = ColorCell(i, j, BACKGROUND)
                cell.clicked.connect(self.on_cell_clicked)
                self.grid.addWidget(cell, i, j)
                self.cells[i][j] = cell
                cell.setAutoFillBackground(True)

        cell_size = min(self.width() // self.cols, self.height() // self.rows)
        for i in range(self.rows):
            for j in range(self.cols):
                self.cells[i][j].setFixedSize(cell_size, cell_size)

    def resizeEvent(self, event):
        cell_size = min(self.width() // self.cols, self.height() // self.rows)
        for i in range(self.rows):
            for j in range(self.cols):
                self.cells[i][j].setFixedSize(cell_size, cell_size)
        self.setFixedSize(self.cols * cell_size, self.rows * cell_size)

    def on_cell_clicked(self, row, col):
        if self.selected_cell:
            prev_row, prev_col = self.selected_cell
            self.cells[prev_row][prev_col].clicked_state = False
            self.cells[prev_row][prev_col].update()

        cell = self.cells[row][col]
        cell.clicked_state = True
        cell.update()
        self.selected_cell = (row, col)
        self.cell_clicked.emit(row, col)

    def setBackgroundImage(self, image_path):
        self.background_image = QPixmap(image_path)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.background_image:
            painter = QPainter(self)
            painter.drawPixmap(self.rect(), self.background_image)


class GridUpdateWorker(QObject):
    updateFinished = pyqtSignal()

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.min_strength = None
        self.max_strength = None

    def get_min_max_strenghts(self):
        for row, col in self.main_window.active_channels:
            seizure_times = self.main_window.data[row - 1, col - 1]["SzEventsTimes"]
            if seizure_times:
                for i, timerange in enumerate(seizure_times):
                    if len(timerange) == 1:
                        start = seizure_times[0][0]
                        stop = seizure_times[1][0]
                    else:
                        start, stop, strength = timerange
                        if self.min_strength is None or strength < self.min_strength:
                            self.min_strength = strength
                        if self.max_strength is None or strength > self.max_strength:
                            self.max_strength = strength

    def normalize_strength(self, strength):
        strength = float(strength)
        return math.sqrt(
            (strength - self.min_strength) / (self.max_strength - self.min_strength)
        )

    def update_grid(self):
        current_time = self.main_window.progress_bar.value() / 4
        if self.min_strength is None or self.max_strength is None:
            self.get_min_max_strenghts()

        for row, col in self.main_window.active_channels:
            cell = self.main_window.grid_widget.cells[row - 1][col - 1]
            se_times = self.main_window.data[row - 1, col - 1]["SE_List"]
            seizure_times = self.main_window.data[row - 1, col - 1]["SzEventsTimes"]

            found_se = False
            found_seizure = False

            if se_times:
                for i, timerange in enumerate(se_times):
                    if len(timerange) == 1:
                        start = se_times[0][0]
                        stop = se_times[1][0]
                        strength = 0  # TODO: Fix this potentially?
                    else:
                        start, stop = timerange
                        strength = self.normalize_strength(seizure_times[i][2])

                    if start <= current_time <= stop:
                        if cell.palette().color(QPalette.Window) != SE:
                            cell.setColor(SE, math.pow(strength, 0.25))
                        found_se = True
                        break

            if not found_se and seizure_times:
                for i, timerange in enumerate(seizure_times):
                    if len(timerange) == 1:
                        start = seizure_times[0][0]
                        stop = seizure_times[1][0]
                        strength = 0
                    else:
                        start, stop, strength = timerange
                        strength = self.normalize_strength(strength)
                    if start <= current_time <= stop:
                        if cell.palette().color(QPalette.Window) != SEIZURE:
                            cell.setColor(SEIZURE, strength)
                        found_seizure = True
                        break

            if not found_se and not found_seizure:
                if cell.palette().color(QPalette.Window) != ACTIVE:
                    cell.setColor(ACTIVE)

        self.updateFinished.emit()


class GraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.plot_widgets = [pg.PlotWidget() for _ in range(4)]
        self.red_lines = [
            pg.InfiniteLine(
                angle=90, movable=False, pen=pg.mkPen(color=(255, 0, 0), width=2)
            )
            for _ in range(4)
        ]

        for i in range(4):
            plot_widget = self.plot_widgets[i]
            red_line = self.red_lines[i]

            plot_widget.showGrid(x=True, y=True)
            plot_widget.setMouseEnabled(x=True, y=True)
            plot_widget.setMenuEnabled(False)
            plot_widget.setClipToView(True)
            plot_widget.setDownsampling(mode="peak")
            plot_widget.setXRange(0, 1000)
            plot_widget.enableAutoRange(axis="y")
            plot_widget.getPlotItem().getViewBox().setLimits(xMin=0, xMax=2**16)
            plot_widget.getPlotItem().getViewBox().setMouseEnabled(x=True, y=True)
            plot_widget.getPlotItem().getViewBox().setMouseMode(pg.ViewBox.RectMode)
            plot_widget.getPlotItem().getViewBox().enableAutoRange(
                axis="xy", enable=True
            )
            plot_widget.getPlotItem().showGrid(x=True, y=True)
            plot_widget.addItem(red_line)
            plot_widget.setObjectName(f"plot_{i}")
            plot_widget.setBackground("w")

            self.layout.addWidget(plot_widget)

        self.plots = [
            plot_widget.plot(pen=pg.mkPen(color=(0, 0, 255), width=1.5))
            for plot_widget in self.plot_widgets
        ]

    def update_red_lines(self, value):
        for red_line in self.red_lines:
            red_line.setPos(value / 4)

    def plot(self, x, y, title, xlabel, ylabel, plot_index, shape):
        downsample_x, downsample_y = self.downsample_data(x, y, 30000)
        self.plots[plot_index].setData(downsample_x, downsample_y)

        if "(" in title:
            title_parts = title.split(" ", 1)
            shape_text = title_parts[0]
            remaining_title = title_parts[1] if len(title_parts) > 1 else ""

            title_text = f'<span style="position: relative; top: 5px; font-size: 20pt; color: #a4161a;">{shape_text}</span> {remaining_title}'
            self.plot_widgets[plot_index].setTitle(title_text)
        else:
            self.plot_widgets[plot_index].setTitle(title)

        self.plot_widgets[plot_index].setLabel("bottom", xlabel)
        self.plot_widgets[plot_index].setLabel("left", ylabel)
        self.plots[plot_index].setPen(pg.mkPen(color=(0, 0, 0), width=1.5))

    def downsample_data(self, x, y, num_points):
        if len(x) <= num_points:
            return x, y

        step = len(x) // num_points
        downsampled_x = x[::step]
        downsampled_y = y[::step]

        return downsampled_x, downsampled_y

    def change_view_mode(self, mode: str):
        if mode == "pan":
            for i in range(4):
                plot_widget = self.plot_widgets[i]
                view_box = plot_widget.getPlotItem().getViewBox()
                view_box.setMouseMode(pg.ViewBox.PanMode)
        else:
            for i in range(4):
                plot_widget = self.plot_widgets[i]
                view_box = plot_widget.getPlotItem().getViewBox()
                view_box.setMouseMode(pg.ViewBox.RectMode)


class HeatmapWidget(QWidget):
    def __init__(self, rows, cols, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(0)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid_layout)
        self.cells = []
        self.createGrid()

    def createGrid(self):
        self.cells = [
            [QLabel(self) for _ in range(self.cols)] for _ in range(self.rows)
        ]
        for i in range(self.rows):
            for j in range(self.cols):
                cell = self.cells[i][j]
                cell.setAutoFillBackground(True)
                self.grid_layout.addWidget(cell, i, j)

    def setHeatmapData(self, data):
        min_value = np.min(data)
        max_value = np.max(data)
        for i in range(self.rows):
            for j in range(self.cols):
                value = data[i][j]
                normalized_value = (value - min_value) / (max_value - min_value)
                color = QColor(0, 255, 0, int(normalized_value * 255))
                palette = self.cells[i][j].palette()
                palette.setColor(QPalette.Window, color)
                self.cells[i][j].setPalette(palette)


class MainWindow(QMainWindow):
    gridUpdateRequested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.file_path = None
        self.tolerance = 40
        self.recording_length = None
        self.time_vector = None
        self.data = None
        self.active_channels = None
        self.selected_channel = None
        self.plotted_channels = [None] * 4
        self.selected_subplot = None
        self.spike_data = None
        self.raster_red_line = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen(color=(255, 0, 0), width=2)
        )
        self.raster_tooltip = None
        self.is_recording_video = False

        self.setWindowTitle("Spatial SE Viewer")
        self.main_layout = QHBoxLayout()
        central_widget = QWidget()
        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)
        self.resize(1567, 832)

        self.menuBar = QMenuBar(self)
        self.menuBar.setNativeMenuBar(False)
        self.setMenuBar(self.menuBar)

        self.fileMenu = QMenu("File", self)
        self.menuBar.addMenu(self.fileMenu)
        self.openAction = QAction("Open file", self)
        self.openAction.triggered.connect(self.openFile)
        self.fileMenu.addAction(self.openAction)
        self.createVideoAction = QAction("Save MEA as video", self)
        self.createVideoAction.triggered.connect(self.create_recording_helper)
        self.fileMenu.addAction(self.createVideoAction)
        self.saveGridAction = QAction("Save MEA as png", self)
        self.saveGridAction.triggered.connect(self.save_grid_as_png)
        self.fileMenu.addAction(self.saveGridAction)
        self.saveChannelPlotsAction = QAction("Save Channel Plots", self)
        self.saveChannelPlotsAction.triggered.connect(self.save_channel_plots)
        self.fileMenu.addAction(self.saveChannelPlotsAction)
        self.saveMeaWithPlotsAction = QAction("Save MEA with Channel Plots", self)
        self.saveMeaWithPlotsAction.triggered.connect(self.save_mea_with_plots)
        self.fileMenu.addAction(self.saveMeaWithPlotsAction)

        self.viewMenu = QMenu("View", self)
        self.menuBar.addMenu(self.viewMenu)
        self.showGridAction = QAction("Show Grid", self, checkable=True)
        self.showGridAction.setChecked(True)
        # self.showGridAction.triggered.connect(self.toggleGrid)
        # self.viewMenu.addAction(self.showGridAction)

        self.left_pane = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_pane.setLayout(self.left_layout)
        self.main_layout.addWidget(self.left_pane)

        self.tab_widget = QTabWidget()
        self.left_layout.addWidget(self.tab_widget)

        self.grid_widget = GridWidget(64, 64)
        self.grid_widget.cell_clicked.connect(self.on_cell_clicked)
        grid_layout = QVBoxLayout()
        grid_layout.addWidget(self.grid_widget)
        grid_layout.setAlignment(Qt.AlignCenter)
        grid_widget_container = QWidget()
        grid_widget_container.setLayout(grid_layout)
        self.tab_widget.addTab(grid_widget_container, "MEA Grid")

        self.second_tab_widget = QWidget()
        self.second_tab_layout = QVBoxLayout()
        self.second_tab_widget.setLayout(self.second_tab_layout)
        self.tab_widget.addTab(self.second_tab_widget, "Raster Plot")

        self.third_tab_widget = QWidget()
        self.third_tab_layout = QVBoxLayout()
        self.third_tab_widget.setLayout(self.third_tab_layout)

        self.todo_label = QLabel("todo")
        self.todo_label.setAlignment(Qt.AlignCenter)
        self.third_tab_layout.addWidget(self.todo_label)

        self.tab_widget.addTab(self.third_tab_widget, "Temp Analysis")
        self.heatmap_widget = HeatmapWidget(64, 64)
        self.third_tab_layout.addWidget(self.heatmap_widget)

        self.second_plot_widget = pg.PlotWidget()
        self.second_plot_widget.setAspectLocked(True)
        self.second_plot_widget.setBackground("w")

        self.second_tab_layout.addWidget(self.second_plot_widget)

        self.tab_widget.currentChanged.connect(self.update_tab_layout)

        self.grid_update_thread = QThread()
        self.grid_update_worker = GridUpdateWorker(self)
        self.grid_update_worker.moveToThread(self.grid_update_thread)
        self.grid_update_worker.updateFinished.connect(self.on_grid_update_finished)
        self.grid_update_thread.start()

        self.gridUpdateRequested.connect(self.grid_update_worker.update_grid)

        self.right_pane = QWidget()
        self.right_layout = QVBoxLayout()
        self.right_pane.setLayout(self.right_layout)
        self.main_layout.addWidget(self.right_pane)

        self.graph_pane = QWidget()
        self.graph_layout = QVBoxLayout()
        self.graph_pane.setLayout(self.graph_layout)
        self.right_layout.addWidget(self.graph_pane)

        self.graph_widget = GraphWidget()
        self.graph_layout.addWidget(self.graph_widget)

        self.settings_pane = QWidget()
        self.settings_layout = QVBoxLayout()
        self.settings_pane.setLayout(self.settings_layout)
        self.right_layout.addWidget(self.settings_pane)

        # Create a new horizontal layout for the opacity slider, checkbox, and order combo box
        self.settings_top_layout = QHBoxLayout()
        self.settings_layout.addLayout(self.settings_top_layout)

        self.opacity_label = QLabel("Image Opacity:")
        self.settings_top_layout.addWidget(self.opacity_label)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setTickPosition(QSlider.TicksBelow)
        self.opacity_slider.setTickInterval(25)
        self.opacity_slider.valueChanged.connect(self.set_grid_opacity)
        self.settings_top_layout.addWidget(self.opacity_slider)

        self.show_seizure_order_checkbox = QCheckBox("Show Seizure Order")
        self.settings_top_layout.addWidget(self.show_seizure_order_checkbox)
        self.show_seizure_order_checkbox.stateChanged.connect(self.toggle_seizure_order)

        self.order_combo = QComboBox()
        self.order_combo.addItems(["Default", "Order by Seizure", "Order by SE"])
        self.settings_top_layout.addWidget(self.order_combo)
        self.order_combo.currentIndexChanged.connect(self.set_raster_order)

        self.control_layout = QHBoxLayout()
        self.settings_layout.addLayout(self.control_layout)

        self.open_button = QPushButton(" Open File")
        self.open_button.clicked.connect(self.openFile)
        self.control_layout.addWidget(self.open_button)

        self.run_button = QPushButton(" Run Analysis")
        self.run_button.clicked.connect(self.run_analysis)
        self.control_layout.addWidget(self.run_button)

        self.clear_button = QPushButton("󰆴 Clear Plots")
        self.control_layout.addWidget(self.clear_button)
        self.clear_button.clicked.connect(self.clear_plots)

        self.bottom_pane = QWidget()
        self.bottom_layout = QHBoxLayout()
        self.bottom_pane.setLayout(self.bottom_layout)
        self.right_layout.addWidget(self.bottom_pane)

        self.playback_layout = QHBoxLayout()
        self.bottom_layout.addLayout(self.playback_layout)

        self.skip_backward_button = QPushButton("")
        self.skip_backward_button.clicked.connect(self.skipBackward)
        self.playback_layout.addWidget(self.skip_backward_button)

        self.prev_frame_button = QPushButton("")
        self.prev_frame_button.clicked.connect(self.prevFrame)
        self.playback_layout.addWidget(self.prev_frame_button)

        self.play_pause_button = QPushButton("")
        self.play_pause_button.clicked.connect(self.playPause)
        self.playback_layout.addWidget(self.play_pause_button)

        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.updatePlayback)

        self.next_frame_button = QPushButton("")
        self.next_frame_button.clicked.connect(self.nextFrame)
        self.playback_layout.addWidget(self.next_frame_button)

        self.skip_forward_button = QPushButton("")
        self.skip_forward_button.clicked.connect(self.skipForward)
        self.playback_layout.addWidget(self.skip_forward_button)

        self.progress_bar = QSlider(Qt.Horizontal)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTickPosition(QSlider.TicksBelow)
        self.progress_bar.valueChanged.connect(self.seekPosition)
        self.playback_layout.addWidget(self.progress_bar)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25", "0.5", "1", "2.0", "4.0", "16.0"])
        self.playback_layout.addWidget(self.speed_combo)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentIndexChanged.connect(self.setPlaybackSpeed)

        self.set_widgets_enabled()

        # Start MATLAB engine
        self.eng = matlab.engine.start_matlab()
        self.eng.eval("parpool('Threads')", nargout=0)

    def update_tab_layout(self, index):
        if not self.is_recording_video:
            if index == 0:
                self.grid_widget.setVisible(True)
                self.second_plot_widget.setVisible(False)
                self.opacity_label.setVisible(True)
                self.opacity_slider.setVisible(True)
            elif index == 1:
                self.grid_widget.setVisible(False)
                self.second_plot_widget.setVisible(True)
                self.second_plot_widget.setGeometry(self.second_tab_widget.rect())
                self.opacity_label.setVisible(False)
                self.opacity_slider.setVisible(False)

    def clear_plots(self):
        for i in range(4):
            if self.plotted_channels[i] is not None:
                self.plotted_channels[i].plotted_state = False
                self.plotted_channels[i].plotted_shape = None
                self.plotted_channels[i].update()
            self.graph_widget.plots[i].setData([], [])
            self.graph_widget.plot_widgets[i].setTitle("Select Channel")
            self.graph_widget.plot_widgets[i].setLabel("bottom", "sec")
            self.graph_widget.plot_widgets[i].setLabel("left", "mV")

        self.grid_widget.update()

    def calculateHeatmapData(self):
        heatmap_data = np.zeros((64, 64))
        for i in range(64):
            for j in range(64):
                if self.data is not None:
                    channel_data = self.data[i, j]
                    seizure_count = 0
                    se_count = 0

                    if channel_data["SE_List"]:
                        se_count = len(channel_data["SE_List"])

                    if channel_data["SzEventsTimes"]:
                        seizure_count = len(channel_data["SzEventsTimes"])

                    heatmap_data[i][j] = seizure_count + se_count

        return heatmap_data

    def detect_spikes(self, channel_data, threshold):
        spike_indices = []
        voltage_data = np.asarray(channel_data["signal"]).squeeze()
        step = 2
        for i, value in enumerate(voltage_data[::step]):
            if value > threshold:
                spike_indices.append(i * step)
        return spike_indices

    def format_spike_data(self, voltage_data, threshold, sampling_rate):
        spike_data = []
        for row in tqdm(range(voltage_data.shape[0]), desc="Processing Channels"):
            for col in range(voltage_data.shape[1]):
                channel_data = voltage_data[row, col]
                spike_indices = self.detect_spikes(channel_data, threshold)
                spike_times = [
                    index / sampling_rate
                    for index in spike_indices
                    if (index / sampling_rate) > 10
                ]
                spike_data.append(spike_times)
        return spike_data

    def toggle_seizure_order(self, state):
        if state == Qt.Checked:
            self.show_seizure_order()
        else:
            self.hide_seizure_order()

    def show_seizure_order(self):
        if self.data is None:
            return

        seizure_order = sorted(
            self.active_channels,
            key=lambda x: self.get_first_seizure_time(x[0] - 1, x[1] - 1),
        )

        for i, (row, col) in enumerate(seizure_order, start=1):
            cell = self.grid_widget.cells[row - 1][col - 1]
            cell.setText(str(i))
            cell.setAlignment(Qt.AlignCenter)
            cell.setStyleSheet("color: white; font-weight: bold;")

    def hide_seizure_order(self):
        for row in range(self.grid_widget.rows):
            for col in range(self.grid_widget.cols):
                cell = self.grid_widget.cells[row][col]
                cell.setText("")
                cell.setStyleSheet("")

    def set_raster_order(self, index):
        if index == 0:
            # Default order
            self.active_channels.sort(key=lambda x: (x[0], x[1]))
        elif index == 1:
            # Order by Seizure
            self.active_channels.sort(
                key=lambda x: self.get_first_seizure_time(x[0] - 1, x[1] - 1)
            )
        elif index == 2:
            # Order by SE
            self.active_channels.sort(
                key=lambda x: self.get_first_se_time(x[0] - 1, x[1] - 1)
            )

        self.update_raster_plot_data()

        if self.show_seizure_order_checkbox.isChecked():
            self.show_seizure_order()
        else:
            self.hide_seizure_order()

    def get_first_seizure_time(self, row, col):
        if self.data is None:
            return float("inf")

        if row < 0 or row >= self.data.shape[0] or col < 0 or col >= self.data.shape[1]:
            print(f"Invalid indices: row={row}, col={col}")
            return float("inf")

        channel_data = self.data[row, col]
        seizure_times = channel_data["SzEventsTimes"]

        if seizure_times:
            if len(seizure_times[0]) == 1:
                return seizure_times[0][0]
            else:
                return seizure_times[0][0]
        else:
            return float("inf")

    def get_first_se_time(self, row, col):
        if self.data is None:
            return float("inf")

        if row < 0 or row >= self.data.shape[0] or col < 0 or col >= self.data.shape[1]:
            print(f"Invalid indices: row={row}, col={col}")
            return float("inf")

        channel_data = self.data[row, col]
        se_times = channel_data["SE_List"]

        if se_times:
            if len(se_times[0]) == 1:
                return se_times[0][0]
            else:
                return se_times[0][0]
        else:
            return float("inf")

    def create_raster_plot(self, sampling_rate):
        if self.data is None:
            return

        self.spike_data = self.format_spike_data(self.data, 0.06, sampling_rate)

        self.second_plot_widget.clear()

        self.raster_plot_items = []
        for row, col in self.active_channels:
            plot_item = pg.ScatterPlotItem(pxMode=False)
            plot_item.setSymbol("|")
            plot_item.setSize(1)
            self.raster_plot_items.append(plot_item)
            self.second_plot_widget.addItem(plot_item)

        self.second_plot_widget.setXRange(0, self.recording_length)
        self.second_plot_widget.setYRange(0, len(self.active_channels))

        self.raster_red_line = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen(color=(255, 0, 0), width=2)
        )
        self.raster_red_line.setPos(self.progress_bar.value() / 4)
        self.second_plot_widget.addItem(self.raster_red_line)

        self.raster_tooltip = pg.TextItem(text="", color=(0, 0, 0), anchor=(0.5, 2))
        self.second_plot_widget.addItem(self.raster_tooltip)
        self.raster_tooltip.hide()

        self.second_plot_widget.scene().sigMouseMoved.connect(
            self.update_raster_tooltip
        )

        self.update_raster_plot_data()

    def update_raster_tooltip(self, pos):
        if self.active_channels:
            if self.second_plot_widget.sceneBoundingRect().contains(pos):
                mouse_point = self.second_plot_widget.getPlotItem().vb.mapSceneToView(
                    pos
                )
                y_pos = mouse_point.y()
                num_channels = len(self.active_channels)
                channel_index = int(num_channels - y_pos - 1)

                if 0 <= channel_index < num_channels:
                    row, col = self.active_channels[channel_index]
                    self.raster_tooltip.setText(f"Channel ({row}, {col})")
                    self.raster_tooltip.setPos(mouse_point)
                    self.raster_tooltip.show()
                else:
                    self.raster_tooltip.hide()
            else:
                self.raster_tooltip.hide()

    def update_raster_plot_data(self):
        num_channels = len(self.active_channels)
        for i, (row, col) in tqdm(
            enumerate(self.active_channels), desc="Updating Raster Plot"
        ):
            if (
                row - 1 < 0
                or row - 1 >= self.data.shape[0]
                or col - 1 < 0
                or col - 1 >= self.data.shape[1]
            ):
                print(f"Invalid indices: row={row}, col={col}")
                continue

            channel_data = self.data[row - 1, col - 1]
            spike_times = self.spike_data[(row - 1) * 64 + (col - 1)]
            spike_colors = []

            for spike_time in spike_times:
                found_se = False
                found_seizure = False

                if channel_data["SE_List"]:
                    for j, timerange in enumerate(channel_data["SE_List"]):
                        if len(timerange) == 1:
                            start = channel_data["SE_List"][0][0]
                            stop = channel_data["SE_List"][1][0]
                        else:
                            start, stop = timerange

                        if start <= spike_time <= stop:
                            spike_colors.append((255, 165, 0))
                            found_se = True
                            break

                if not found_se and channel_data["SzEventsTimes"]:
                    for j, timerange in enumerate(channel_data["SzEventsTimes"]):
                        if len(timerange) == 1:
                            start = channel_data["SzEventsTimes"][0][0]
                            stop = channel_data["SzEventsTimes"][1][0]
                        else:
                            start, stop, strength = timerange

                        if start <= spike_time <= stop:
                            spike_colors.append((0, 0, 255))
                            found_seizure = True
                            break

                if not found_se and not found_seizure:
                    spike_colors.append((0, 0, 0))

            y_position = num_channels - i - 1
            # print(f"Y Position: {y_position} for channel ({row}, {col})")
            self.raster_plot_items[i].setData(
                spike_times, np.full(len(spike_times), y_position), pen=spike_colors
            )

    def on_grid_update_finished(self):
        self.grid_widget.update()

    def set_grid_opacity(self, value):
        opacity = value / 100.0
        for row in range(self.grid_widget.rows):
            for col in range(self.grid_widget.cols):
                cell = self.grid_widget.cells[row][col]
                palette = cell.palette()
                color = palette.color(QPalette.Window)
                color.setAlphaF(opacity)
                palette.setColor(QPalette.Window, color)
                cell.setPalette(palette)

    def deselect_cell(self):
        if self.selected_channel is not None:
            row, col = self.selected_channel
            self.grid_widget.cells[row][col].clicked_state = False
            self.grid_widget.cells[row][col].update()
            self.selected_channel = None

    def mousePressEvent(self, event):
        if not self.grid_widget.underMouse() and not self.is_recording_video:
            self.deselect_cell()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key_mapping = [Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4]
        shape_mapping = ["", "󰔷", "x", ""]
        if event.key() in key_mapping:
            index = key_mapping.index(event.key())
            if self.selected_channel is not None:
                row, col = self.selected_channel
                if self.data is not None:
                    if self.plotted_channels[index] is not None:
                        self.plotted_channels[index].plotted_state = False
                        self.plotted_channels[index].plotted_shape = None
                        self.plotted_channels[index].update()
                    self.plotted_channels[index] = self.grid_widget.cells[row][col]
                    self.plotted_channels[index].plotted_state = True
                    self.plotted_channels[index].plotted_shape = shape_mapping[index]
                    self.plotted_channels[index].update()

                self.graph_widget.plot(
                    self.time_vector,
                    np.asarray(self.data[row, col]["signal"]).squeeze(),
                    f"{shape_mapping[index]} Channel ({row + 1}, {col + 1})",
                    "",
                    "mV",
                    index,
                    shape_mapping[index],
                )

                self.grid_widget.cells[row][col].clicked_state = False
                self.grid_widget.cells[row][col].update()
                self.selected_channel = None
        else:
            if event.key() == Qt.Key_Shift:
                print("Pressed shift!")
                self.graph_widget.change_view_mode("pan")
            elif event.key() == Qt.Key_C:
                current_time = self.progress_bar.value() / 4
                for plot_widget in self.graph_widget.plot_widgets:
                    view_box = plot_widget.getPlotItem().getViewBox()
                    x_range = view_box.viewRange()[0]
                    x_width = x_range[1] - x_range[0]
                    x_min = current_time - x_width / 2
                    x_max = current_time + x_width / 2
                    view_box.setRange(xRange=(x_min, x_max), padding=0)
            elif event.key() == Qt.Key_Right:
                if self.skip_backward_button.isEnabled():
                    self.nextFrame()
            elif event.key() == Qt.Key_Left:
                if self.skip_forward_button.isEnabled():
                    self.prevFrame()
            elif event.key() == Qt.Key_Space:
                if self.play_pause_button.isEnabled():
                    self.playPause()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Shift:
            print("Let go of shift!")
            self.graph_widget.change_view_mode("rect")

    def on_cell_clicked(self, row, col):
        print(f"Cell clicked: ({row}, {col})")
        if self.selected_channel:
            prev_row, prev_col = self.selected_channel
            self.grid_widget.cells[prev_row][prev_col].clicked_state = False
            self.grid_widget.cells[prev_row][prev_col].update()
        self.selected_channel = (row, col)

    def set_widgets_enabled(self):
        if self.file_path is not None:
            self.run_button.setEnabled(True)
        else:
            self.run_button.setEnabled(False)

        if self.data is not None:
            self.clear_button.setEnabled(True)
            self.skip_backward_button.setEnabled(True)
            self.prev_frame_button.setEnabled(True)
            self.play_pause_button.setEnabled(True)
            self.next_frame_button.setEnabled(True)
            self.skip_forward_button.setEnabled(True)
            self.progress_bar.setEnabled(True)
            self.speed_combo.setEnabled(True)
            self.order_combo.setEnabled(True)
            self.saveGridAction.setEnabled(True)
            self.createVideoAction.setEnabled(True)
            self.saveChannelPlotsAction.setEnabled(True)
            self.saveMeaWithPlotsAction.setEnabled(True)
        else:
            self.clear_button.setEnabled(False)
            self.skip_backward_button.setEnabled(False)
            self.prev_frame_button.setEnabled(False)
            self.play_pause_button.setEnabled(False)
            self.next_frame_button.setEnabled(False)
            self.skip_forward_button.setEnabled(False)
            self.progress_bar.setEnabled(False)
            self.speed_combo.setEnabled(False)
            self.order_combo.setEnabled(False)
            self.saveGridAction.setEnabled(False)
            self.createVideoAction.setEnabled(False)
            self.saveChannelPlotsAction.setEnabled(False)
            self.saveMeaWithPlotsAction.setEnabled(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjustGridSize()
        self.second_plot_widget.setGeometry(self.second_tab_widget.rect())

    def adjustGridSize(self):
        window_width = self.width()
        window_height = self.height()

        left_pane_size = min(window_width // 2, window_height)

        self.left_pane.setFixedSize(left_pane_size, left_pane_size)

        margin = 20
        widget_size = left_pane_size - 2 * margin
        self.grid_widget.setFixedSize(widget_size, widget_size)

    def openFile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            directory="/Users/booka66/Jake-Squared/Sz_SE_Detection/",
            filter="BRW Files (*.brw)",
        )
        if file_path:
            print("Selected file path:", file_path)
            self.file_path = file_path

            try:
                baseName = os.path.basename(file_path)

                brwFileName = os.path.basename(file_path)
                dateSlice = "_".join(brwFileName.split("_")[:4])
                dateSliceNumber = (
                    dateSlice.split("slice")[0]
                    + "slice"
                    + dateSlice.split("slice")[1][:1]
                )
                imageName = f"{dateSliceNumber}_pic_cropped.jpg"
                print(f"Trying to find image: {imageName}")
                imageFolder = os.path.dirname(file_path)
                image_path = os.path.join(imageFolder, imageName)

                if os.path.exists(image_path):
                    self.grid_widget.setBackgroundImage(image_path)
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
                    )
                    if imageFileName:
                        self.grid_widget.setBackgroundImage(image_path)
                    else:
                        print("No image selected")
            except Exception as e:
                print(f"Error: {e}")

        self.set_widgets_enabled()

    def get_channels(self):
        with h5py.File(self.file_path, "r") as f:
            recElectrodeList = f["/3BRecInfo/3BMeaStreams/Raw/Chs"]
            rows = recElectrodeList["Row"][()]
            cols = recElectrodeList["Col"][()]
        return rows, cols

    def create_grid(self):
        for row in self.grid_widget.cells:
            for cell in row:
                cell.setColor(BACKGROUND)
        for row, col in self.active_channels:
            self.grid_widget.cells[row - 1][col - 1].setColor(ACTIVE)

    def update_grid(self):
        self.gridUpdateRequested.emit()

    def run_analysis(self):
        try:
            if self.data is not None:
                alert = QMessageBox(self)
                alert.setText(
                    "Loaded analysis will be deleted. Are you sure you would like to continue?"
                )
                alert.setStandardButtons(QMessageBox.Yes | QMessageBox.Abort)
                alert.setIcon(QMessageBox.Warning)
                button = alert.exec()

                if button == QMessageBox.Abort:
                    return
                else:
                    self.clear_plots()
                    self.grid_update_worker.min_strength = None
                    self.grid_update_worker.max_strength = None
                    self.recording_length = None
                    self.time_vector = None
                    self.data = None
                    self.active_channels = []
                    self.selected_channel = []
                    self.plotted_channels = [None] * 4
                    self.selected_subplot = None
                    self.spike_data = []
                    self.create_grid()
                    self.set_widgets_enabled()

            self.run_button.setEnabled(False)
            time.sleep(0.5)
            self.update()
            start_time_1 = perf_counter()
            print("Beginning analysis...")
            data_cell, total_channels, sampling_rate, num_rec_frames = (
                self.eng.vectorized_state_extractor(self.file_path, nargout=4)
            )
            end_time_1 = perf_counter()
            print(f"State extraction complete in {end_time_1 - start_time_1} seconds")

            total_channels = int(total_channels)
            sampling_rate = float(sampling_rate)
            num_rec_frames = int(num_rec_frames)

            data_np = np.array(data_cell)

            self.data = data_np.reshape((64, 64))

            # Access individual elements of data_2d
            # for i in range(64):
            #     for j in range(64):
            #         signal = data_2d[i, j]["signal"]
            #         name = data_2d[i, j]["name"]
            #         sz_events_times = data_2d[i, j]["SzEventsTimes"]
            #         se_list = data_2d[i, j]["SE_List"]

            self.recording_length = (1 / sampling_rate) * (num_rec_frames - 1)
            self.time_vector = [i / sampling_rate for i in range(num_rec_frames)]
            self.progress_bar.setRange(0, int(self.recording_length) * 4)

            self.progress_bar.setTickInterval(int(self.recording_length / 5))

            # print("Data shape:", self.data.shape)
            # print("Total channels:", total_channels)
            # print("Sampling rate:", sampling_rate)
            # print("Number of recording frames:", num_rec_frames)
            # print("Recording length:", self.recording_length)

            rows, cols = self.get_channels()
            self.active_channels = list(zip(rows, cols))

            self.create_grid()
            self.update_grid()

            start_time_2 = perf_counter()
            print("Generating raster plot...")
            self.create_raster_plot(sampling_rate)
            end_time_2 = perf_counter()
            print(f"Raster plot generated in {end_time_2 - start_time_2} seconds")

            title = "Select Channel"
            for i in range(4):
                self.graph_widget.plot(
                    [],
                    [],
                    title,
                    "sec",
                    "mV",
                    i,
                    "",
                )

            for i in range(1, 4):
                self.graph_widget.plot_widgets[i].setXLink(
                    self.graph_widget.plot_widgets[0]
                )
                self.graph_widget.plot_widgets[i].setYLink(
                    self.graph_widget.plot_widgets[0]
                )

            heatmap_data = self.calculateHeatmapData()
            self.heatmap_widget.setHeatmapData(heatmap_data)

            self.set_widgets_enabled()

            print(f"Analysis complete in {end_time_2 - start_time_1} seconds")

            sound_thread = threading.Thread(
                target=self.play_sound, args=("../success.mp3",)
            )
            sound_thread.start()

        except Exception as e:
            sound_thread = threading.Thread(
                target=self.play_sound, args=("../fail.mp3",)
            )
            sound_thread.start()

            print(f"Error: {e}")

    def play_sound(self, file):
        playsound(file)

    def skipBackward(self):
        print("Skip Backward")
        next_index = self.progress_bar.value() - int(self.recording_length * 4 / 10)
        if next_index < 0:
            next_index = 0
        self.progress_bar.setValue(next_index)

    def prevFrame(self):
        print("Previous Frame")
        if self.progress_bar.value() > 0:
            self.progress_bar.setValue(self.progress_bar.value() - 1)
            self.update_grid()

    def playPause(self):
        if self.play_pause_button.text() == "":
            self.play_pause_button.setText("")
            print("Play")
            self.playback_timer.start(100)
        else:
            self.play_pause_button.setText("")
            print("Pause")
            self.playback_timer.stop()

    def updatePlayback(self):
        speed = float(self.speed_combo.currentText())
        skip_frames = int(speed * 4)

        current_value = self.progress_bar.value()
        next_value = current_value + skip_frames

        if next_value <= self.progress_bar.maximum():
            self.progress_bar.setValue(next_value)
        else:
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.playback_timer.stop()
            self.play_pause_button.setText("")

    def nextFrame(self):
        print("Next Frame")
        if self.progress_bar.value() < self.progress_bar.maximum():
            self.progress_bar.setValue(self.progress_bar.value() + 1)
            self.update_grid()

    def skipForward(self):
        print("Skip Forward")
        next_index = self.progress_bar.value() + int(self.recording_length * 4 / 10)
        if next_index > self.progress_bar.maximum():
            next_index = self.progress_bar.maximum()
        self.progress_bar.setValue(next_index)

    def setPlaybackSpeed(self, index):
        interval = 100  # Sort of similar to FPS/ticks
        self.playback_timer.setInterval(interval)

    def seekPosition(self, value):
        self.update_grid()
        self.graph_widget.update_red_lines(value)
        self.raster_red_line.setPos(value / 4)

    def save_mea_with_plots(self):
        options = QFileDialog.Options()
        default_filename = "mea_with_plots.svg"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save MEA with Channel Plots",
            default_filename,
            "SVG Files (*.svg)",
            options=options,
        )

        if file_path:
            # Create a dialog to select the channels to save
            channel_dialog = QDialog(self)
            channel_dialog.setWindowTitle("Select Channels")
            channel_layout = QVBoxLayout()

            channel_checkboxes = []
            for i in range(4):
                if self.plotted_channels[i] is not None:
                    row, col = (
                        self.plotted_channels[i].row,
                        self.plotted_channels[i].col,
                    )
                    checkbox = QCheckBox(f"Channel ({row + 1}, {col + 1})")
                    checkbox.setChecked(True)
                    channel_layout.addWidget(checkbox)
                    channel_checkboxes.append(checkbox)

            select_all_checkbox = QCheckBox("Select All")
            select_all_checkbox.setChecked(True)
            select_all_checkbox.stateChanged.connect(
                lambda state: self.select_all_channels(state, channel_checkboxes)
            )
            channel_layout.addWidget(select_all_checkbox)

            button_layout = QHBoxLayout()
            ok_button = QPushButton("OK")
            ok_button.clicked.connect(channel_dialog.accept)
            button_layout.addWidget(ok_button)
            cancel_button = QPushButton("Cancel")
            cancel_button.clicked.connect(channel_dialog.reject)
            button_layout.addWidget(cancel_button)

            channel_layout.addLayout(button_layout)
            channel_dialog.setLayout(channel_layout)

            if channel_dialog.exec() == QDialog.Accepted:
                selected_plots = []
                for i, checkbox in enumerate(channel_checkboxes):
                    if checkbox.isChecked():
                        selected_plots.append(self.graph_widget.plot_widgets[i])

                if selected_plots:
                    self.save_mea_with_selected_plots(selected_plots, file_path)

    def save_mea_with_selected_plots(self, selected_plots, file_path):
        mea_width = self.grid_widget.width()
        mea_height = self.grid_widget.height()
        plot_width = selected_plots[0].width()
        plot_height = selected_plots[0].height()
        grid_size = int(math.ceil(math.sqrt(len(selected_plots))))
        image_width = mea_width + (plot_width * grid_size)
        image_height = max(mea_height, plot_height * grid_size)

        # Create a QImage to render the MEA grid and selected plots
        image = QImage(image_width, image_height, QImage.Format_ARGB32)
        image.fill(Qt.white)

        painter = QPainter(image)

        # Render MEA grid
        grid_pixmap = self.grid_widget.grab()
        painter.drawPixmap(0, 0, grid_pixmap)

        # Render selected channel plots
        for i, plot_widget in enumerate(selected_plots):
            row = i // grid_size
            col = i % grid_size
            x = mea_width + (col * plot_width)
            y = row * plot_height
            plot_pixmap = plot_widget.grab(QRect(0, 0, plot_width, plot_height))
            painter.drawPixmap(x, y, plot_pixmap)

        painter.end()

        # Save the rendered image as SVG
        svg_generator = QSvgGenerator()
        svg_generator.setFileName(file_path)
        svg_generator.setSize(QSize(image_width, image_height))
        svg_generator.setViewBox(QRect(0, 0, image_width, image_height))

        svg_painter = QPainter(svg_generator)
        svg_painter.drawImage(QRect(0, 0, image_width, image_height), image)
        svg_painter.end()

    def save_channel_plots(self):
        options = QFileDialog.Options()
        default_filename = "channel_plots.svg"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Channel Plots",
            default_filename,
            "SVG Files (*.svg)",
            options=options,
        )

        if file_path:
            # Create a dialog to select the channels to save
            channel_dialog = QDialog(self)
            channel_dialog.setWindowTitle("Select Channels")
            channel_layout = QVBoxLayout()

            channel_checkboxes = []
            for i in range(4):
                if self.plotted_channels[i] is not None:
                    row, col = (
                        self.plotted_channels[i].row,
                        self.plotted_channels[i].col,
                    )
                    checkbox = QCheckBox(f"Channel ({row + 1}, {col + 1})")
                    checkbox.setChecked(True)
                    channel_layout.addWidget(checkbox)
                    channel_checkboxes.append(checkbox)

            select_all_checkbox = QCheckBox("Select All")
            select_all_checkbox.setChecked(True)
            select_all_checkbox.stateChanged.connect(
                lambda state: self.select_all_channels(state, channel_checkboxes)
            )
            channel_layout.addWidget(select_all_checkbox)

            button_layout = QHBoxLayout()
            ok_button = QPushButton("OK")
            ok_button.clicked.connect(channel_dialog.accept)
            button_layout.addWidget(ok_button)
            cancel_button = QPushButton("Cancel")
            cancel_button.clicked.connect(channel_dialog.reject)
            button_layout.addWidget(cancel_button)

            channel_layout.addLayout(button_layout)
            channel_dialog.setLayout(channel_layout)

            if channel_dialog.exec() == QDialog.Accepted:
                selected_plots = []
                for i, checkbox in enumerate(channel_checkboxes):
                    if checkbox.isChecked():
                        selected_plots.append(self.graph_widget.plot_widgets[i])

                if selected_plots:
                    self.save_plots_to_svg(selected_plots, file_path)

    def select_all_channels(self, state, channel_checkboxes):
        for checkbox in channel_checkboxes:
            checkbox.setChecked(state == Qt.Checked)

    def save_plots_to_svg(self, selected_plots, file_path):
        if len(selected_plots) == 1:
            # Save a single plot
            plot_widget = selected_plots[0]
            plot_width = plot_widget.width()
            plot_height = plot_widget.height()

            svg_generator = QSvgGenerator()
            svg_generator.setFileName(file_path)
            svg_generator.setSize(QSize(plot_width, plot_height))
            svg_generator.setViewBox(QRect(0, 0, plot_width, plot_height))

            painter = QPainter(svg_generator)
            plot_widget.render(
                painter, QRectF(0, 0, plot_width, plot_height), plot_widget.rect()
            )
            painter.end()
        else:
            # Save multiple plots in a grid
            grid_size = int(math.ceil(math.sqrt(len(selected_plots))))
            plot_width = selected_plots[0].width()
            plot_height = selected_plots[0].height()
            image_width = grid_size * plot_width
            image_height = grid_size * plot_height

            svg_generator = QSvgGenerator()
            svg_generator.setFileName(file_path)
            svg_generator.setSize(QSize(image_width, image_height))
            svg_generator.setViewBox(QRect(0, 0, image_width, image_height))

            painter = QPainter(svg_generator)
            painter.fillRect(QRect(0, 0, image_width, image_height), Qt.white)

            for i, plot_widget in enumerate(selected_plots):
                row = i // grid_size
                col = i % grid_size
                x = col * plot_width
                y = row * plot_height
                painter.save()
                painter.translate(x, y)
                plot_widget.render(
                    painter, QRectF(0, 0, plot_width, plot_height), plot_widget.rect()
                )
                painter.restore()

            painter.end()

    def save_grid_as_png(self):
        if self.file_path:
            default_filename = os.path.splitext(self.file_path)[0] + "_grid.png"
        else:
            default_filename = "grid.png"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Grid as PNG",
            default_filename,
            "PNG Files (*.png)",
        )

        if file_path:
            pixmap = self.grid_widget.grab()
            pixmap.save(file_path, "PNG")

    def create_recording_helper(self):
        if sys.platform == "darwin":  # macOS
            output_path = self.file_path.replace(".brw", ".mov")
        elif sys.platform == "win32":  # Windows
            output_path = self.file_path.replace(".brw", ".mp4")
        else:
            raise ValueError("Unsupported operating system")

        time_step = 10  # Capture frames every 0.25 * x seconds

        self.is_recording_video = True
        self.grid_widget.setMouseTracking(False)

        self.create_grid_recording(output_path, time_step=time_step)

        self.grid_widget.setMouseTracking(True)
        self.is_recording_video = False

    def create_grid_recording(self, output_path, fps=30, time_step=1):
        self.is_recording_video = True

        # Determine the operating system
        if sys.platform == "darwin":  # macOS
            outputdict = {
                "-r": str(fps),
                "-vcodec": "prores",
                "-profile:v": "3",
                "-pix_fmt": "yuv422p10le",
            }

            # Create a writer object with the appropriate codec and container
            writer = skvideo.io.FFmpegWriter(output_path, outputdict=outputdict)

            self.grid_widget.setMouseTracking(False)

            # Capture frames at regular intervals based on the time step
            num_frames = int(self.recording_length / time_step)
            for i in tqdm(range(num_frames), desc="Creating Video"):
                # Set the progress bar value to capture the current frame
                self.progress_bar.setValue(i * time_step * 4)
                QApplication.processEvents()

                # Capture the grid widget as a QPixmap
                pixmap = self.grid_widget.grab()

                # Convert the QPixmap to a QImage
                qimage = pixmap.toImage()

                # Convert the QImage to a numpy array
                image_np = self.qimage_to_numpy(qimage)

                # Write the frame to the video file
                writer.writeFrame(image_np)

            # Close the writer
            writer.close()

        elif sys.platform == "win32":  # Windows
            # Create an MSS object for capturing the screen
            sct = mss()

            # Get the dimensions of the grid widget
            grid_widget_rect = self.grid_widget.rect()
            grid_widget_pos = self.grid_widget.mapToGlobal(grid_widget_rect.topLeft())
            width, height = grid_widget_rect.width(), grid_widget_rect.height()

            # Specify the region of the screen to record
            monitor = {
                "top": grid_widget_pos.y(),
                "left": grid_widget_pos.x(),
                "width": width,
                "height": height,
            }

            # Specify the video codec and compression settings
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            self.grid_widget.setMouseTracking(False)

            # Capture frames at regular intervals based on the time step
            num_frames = int(self.recording_length / time_step)
            for i in tqdm(range(num_frames), desc="Creating Video"):
                # Set the progress bar value to capture the current frame
                self.progress_bar.setValue(i * time_step * 4)
                QApplication.processEvents()

                # Capture the grid widget region
                img = np.array(sct.grab(monitor))

                # Convert the image from BGR to RGB
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

                # Write the frame to the video file
                writer.write(img)

            # Release the VideoWriter
            writer.release()

        else:
            raise ValueError("Unsupported operating system")

        self.grid_widget.setMouseTracking(True)
        self.is_recording_video = False

    def qimage_to_numpy(self, qimage):
        # Convert the QImage to a numpy array
        qimage = qimage.convertToFormat(QImage.Format_RGB888)
        width, height = qimage.width(), qimage.height()
        bytes_per_line = 3 * width
        qimage_data = qimage.bits().asarray(bytes_per_line * height)
        return np.frombuffer(qimage_data, dtype=np.uint8).reshape((height, width, 3))


def install_font(font_url, font_dir):
    zip_path = os.path.join(font_dir, "temp.zip")
    os.makedirs(font_dir, exist_ok=True)
    call(["curl", "-L", "-o", zip_path, font_url])
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith(".ttf") or file.endswith(".otf"):
                zip_ref.extract(file, font_dir)
    os.remove(zip_path)


font_name = "Hack Nerd Font Mono"
font_url = "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.2.1/Hack.zip"

if sys.platform == "darwin":  # macOS
    font_dir = "/Library/Fonts/"
elif sys.platform == "win32":  # Windows
    font_dir = os.path.join(os.environ["WINDIR"], "Fonts")
else:
    print("Unsupported operating system.")
    sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    if not any(font_name in font for font in QFontDatabase().families()):
        print(f"Installing font: {font_name}")
        install_font(font_url, font_dir)
        font_files = []
        for file in os.listdir(font_dir):
            if (file.endswith(".ttf") or file.endswith(".otf")) and font_name.split(
                " "
            )[0] in file:
                font_files.append(file)
        for font_file in font_files:
            font_id = QFontDatabase.addApplicationFont(
                os.path.join(font_dir, font_file)
            )
            if font_id != -1:
                print(f"Installed font: {font_file}")
                font_name = QFontDatabase.applicationFontFamilies(font_id)[0]
                print(f"Font name: {font_name}")
                font = QFont(font_name, 13)
                app.setFont(font)
                break
        else:
            print("Failed to install font")
            sys.exit(1)
    else:
        print(f"Font already installed: {font_name}")
        font = QFont(font_name, 13)
        app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
