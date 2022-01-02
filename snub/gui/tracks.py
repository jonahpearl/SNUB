from PyQt5.QtCore import QDir, Qt, QUrl, pyqtSignal, QTimer
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5 import QtWidgets
from PyQt5 import QtGui
from PyQt5 import QtCore
import sys, os, cv2, json
import numpy as np
import cmapy
import time



class Raster(QWidget):
    def __init__(self, parent, data_path=None, project_directory=None, height_ratio=1, name="",
                 vmin=0, vmax=1, colormap='viridis', downsample_options=np.array([1,10,100]), 
                 max_display_resolution=2000, labels=[], label_margin=10, max_label_width=100, 
                 max_label_height=20, label_color=(255,255,255), label_font_size=12,
                 title_color=(255,255,255), title_margin=5, title_font_size=14, title_height=30):

        super().__init__()
        self.trackStack = parent
        self.vmin,self.vmax = vmin,vmax
        self.colormap = colormap
        self.labels = labels
        self.name = name
        self.height_ratio = height_ratio
        self.downsample_options = downsample_options
        self.max_display_resolution = max_display_resolution
        self.label_margin = 10
        self.max_label_width = max_label_width
        self.max_label_height = max_label_height
        self.label_color = label_color
        self.label_font_size = label_font_size
        self.title_color = title_color
        self.title_margin = title_margin
        self.title_font_size = title_font_size
        self.title_height = title_height

        assert data_path is not None and project_directory is not None
        self.data = np.load(project_directory+'/'+data_path)
        self.row_order = np.arange(self.data.shape[0])
        self.setup_context_menu()
        self.update_image_data()
        self.initUI()

    def setup_context_menu(self):
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        for name,slot in [('Reorder by selection', self.reorder_by_selection),
                          ('Restore original order', self.restore_original_order)]:
            
            label = QLabel(name)
            label.setStyleSheet("""
            QLabel { background-color : #3E3E3E; padding: 10px 12px 10px 12px;}
            QLabel:hover { background-color: #999999;} """)
            action = QWidgetAction(self)
            action.setDefaultWidget(label)
            action.triggered.connect(slot)
            self.addAction(action)

    def reorder_by_selection(self):
        bounds = self.parent().bounds
        mask = self.parent().selection_mask>0
        activation = self.data[:,bounds[0]:bounds[1]][:,mask].mean(1)
        self.update_row_order(np.argsort(activation)[::-1])

    def restore_original_order(self):
        self.update_row_order(np.arange(self.data.shape[0]))

    def update_row_order(self, order):
        self.row_order = order
        self.update_image_data()
 
    def update_image_data(self):
        data_scaled = np.clip((self.data[self.row_order]-self.vmin)/(self.vmax-self.vmin),0,1)*255
        self.image_data = cv2.applyColorMap(data_scaled.astype(np.uint8), cmapy.cmap(self.colormap))[:,:,::-1]
        self.update()

    def initUI(self):
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setVerticalStretch(self.height_ratio)
        self.setSizePolicy(sizePolicy)
        self.setMinimumSize(1,1)
        self.update()

    def cvImage_to_Qimage(self, cvImage):
        height, width, channel = cvImage.shape
        bytesPerLine = 3 * width
        img_data = np.require(cvImage, np.uint8, 'C')
        return QImage(img_data, width, height, bytesPerLine, QImage.Format_RGB888)

    def get_current_pixmap(self):
        ### NOTE: CAN BE ABSTRACTED: SEE SIMILAR TIMELINE METHOD
        current_range = self.trackStack.current_range
        visible_range = current_range[1]-current_range[0]
        best_downsample = np.min(np.nonzero(visible_range / self.downsample_options < self.max_display_resolution)[0])
        downsample = self.downsample_options[best_downsample]
        cropped_image = self.image_data[:,current_range[0]:current_range[1]][:,::downsample]
        return  QPixmap(self.cvImage_to_Qimage(cropped_image))

    def paintEvent(self, event):
        qp = QPainter(self)
        pixmap = self.get_current_pixmap().scaled(self.size()) #, transformMode=QtCore.Qt.SmoothTransformation)

        qp.setRenderHint(QPainter.Antialiasing)
        qp.drawPixmap(QtCore.QPoint(0,0), pixmap)
        qp.setPen(QColor(*self.label_color))
        qp.setFont(QFont("Helvetica [Cronyx]", self.label_font_size))
        for i,label in self.labels:
            height = (self.row_order==i).nonzero()[0][0]
            center_height = (height+.5)/self.data.shape[0]*self.height()
            qp.drawText(self.label_margin, center_height-self.max_label_height//2, 
                self.max_label_width, self.max_label_height, Qt.AlignVCenter, label)

        # qp.rotate(90)
        # qp.setPen(QColor(*self.title_color))
        # qp.setFont(QFont("Helvetica [Cronyx]", self.title_font_size))
        # qp.drawText(self.title_margin, 0, self.title_margin+self.title_height, self.height(), Qt.AlignVCenter, self.name)


class Timeline(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.trackStack = parent
        self.TICK_SPACING_OPTIONS = np.array([1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000])
        self.MAX_TICKS_VISIBLE = 20
        self.HEIGHT = 30
        self.TICK_HEIGHT = 10
        self.TICK_LABEL_WIDTH = 100
        self.TICK_LABEL_MARGIN = 2
        self.TICK_LABEL_HEIGHT = 10
        self.initUI()

    def initUI(self):
        self.setFixedHeight(self.HEIGHT)
        # Set Background
        pal = QPalette()
        pal.setColor(QPalette.Background, QColor(20,20,20))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

    def get_visible_tick_positions(self):
        ### NOTE: CAN BE ABSTRACTED: SEE SIMILAR RASTER METHOD
        current_range = self.trackStack.current_range
        visible_range = current_range[1]-current_range[0]
        best_spacing = np.min(np.nonzero(visible_range/self.TICK_SPACING_OPTIONS < self.MAX_TICKS_VISIBLE)[0])
        tick_interval = self.TICK_SPACING_OPTIONS[best_spacing]
        first_tick = current_range[0] - current_range[0]%tick_interval + tick_interval
        abs_tick_positions = np.arange(first_tick,current_range[1],tick_interval)
        rel_tick_positions = (abs_tick_positions-current_range[0])/visible_range*self.width()
        return abs_tick_positions.astype(int),rel_tick_positions.astype(int)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        qp.setPen(QColor(150, 150, 150))
        qp.setFont(QFont("Helvetica [Cronyx]", 10))
        qp.setRenderHint(QPainter.Antialiasing)
        abs_tick_positions,rel_tick_positions = self.get_visible_tick_positions()
        for a,r in zip(abs_tick_positions,rel_tick_positions): 
            qp.drawLine(r,0,r,self.TICK_HEIGHT)
            qp.drawText(
                r-self.TICK_LABEL_WIDTH//2,
                self.TICK_HEIGHT+self.TICK_LABEL_MARGIN,
                self.TICK_LABEL_WIDTH,
                self.TICK_LABEL_HEIGHT,
                Qt.AlignHCenter, str(a))
        qp.end()


class TrackOverlay(QWidget):
    def __init__(self, parent, vlines={}):
        super().__init__(parent=parent)
        self.vlines = vlines
        self.selection_intervals = []
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def set_selection_intervals(self, selection_mask, bounds):
        diff = np.diff(np.pad(selection_mask, (1,1)))
        starts = (diff>0).nonzero()[0]+bounds[0]
        ends = (diff<0).nonzero()[0]+bounds[0]
        self.selection_intervals = list(zip(starts,ends))

    def paintEvent(self, event):
        self.resize(self.parent().size())
        qp = QPainter()
        qp.begin(self)
        for key,vline in self.vlines.items():
            qp.setPen(QPen(QColor(*vline['color']),vline['linewidth']))
            r = self.parent().abs_to_rel(vline['position'])
            if r > 0 and r < self.width():
                qp.drawLine(r,0,r,self.parent().height())

        qp.setPen(QPen(QColor(255,255,255,150), 1))
        qp.setBrush(QBrush(QColor(255,255,255,100), Qt.SolidPattern))
        for s,e in self.selection_intervals:
            s_rel = self.parent().abs_to_rel(s)
            e_rel = self.parent().abs_to_rel(e)
            if e_rel > 0 or s_rel < self.width() and e_rel > s_rel:
                qp.drawRect(s_rel, 0, e_rel-s_rel, self.height())

        qp.end()


class TrackStack(QWidget):
    new_current_position = pyqtSignal(int)

    def __init__(self, parent, bounds=[0,1], zoom_gain=0.02, min_range=30):
        super().__init__(parent=parent)
        self.mainWindow = parent
        self.zoom_gain = zoom_gain
        self.min_range = min_range
        self.bounds = bounds
        self.current_range = self.bounds
        self.tracks = [Timeline(self)]
        self.selection_mask = np.zeros(bounds[1]-bounds[0])
        self.selection_drag_mode = 0 # +1 for shift-click, -1 for command-click
        self.selection_drag_initial_position = None
        self.new_current_position.connect(self.update_current_position)

    def initUI(self, vlines={}):
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(2)
        self.setSizePolicy(sizePolicy)

        hbox = QHBoxLayout(self)
        splitter = QSplitter(Qt.Vertical)
        for track in self.tracks:
            splitter.addWidget(track)
        hbox.addWidget(splitter)
        self.overlay = TrackOverlay(self, vlines=vlines)
        self.overlay.vlines['cursor'] = {'position':0, 'color':(250,250,250), 'linewidth':1}
        self.update_all()


    def add_track(self, track):
        self.tracks.insert(0,track)

    def wheelEvent(self,event):
        # vertical motion -> zoom
        abs_event_pos = self.rel_to_abs(event.x())
        delta_y = int(np.around(event.pixelDelta().y()/2))
        scale_change = max(1+delta_y*self.zoom_gain, self.min_range/(self.current_range[1]-self.current_range[0]))
        new_range = [
            max(int((self.current_range[0]-abs_event_pos)*scale_change+abs_event_pos),self.bounds[0]),
            min(int((self.current_range[1]-abs_event_pos)*scale_change+abs_event_pos),self.bounds[1])]
        # horizontal motion -> pan
        abs_delta = np.clip((-event.pixelDelta().x())/self.width()*(new_range[1]-new_range[0]),
            self.bounds[0]-new_range[0],self.bounds[1]-new_range[1])
        new_range = [ int(new_range[0]+abs_delta),int(new_range[1]+abs_delta)]
        # update range
        self.update_current_range(new_range=new_range)


    def mouseMoveEvent(self, event):
        position = int(self.rel_to_abs(event.x()))
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers == QtCore.Qt.ShiftModifier:
            self.selection_drag_move(position, 1)
        elif modifiers == QtCore.Qt.ControlModifier:
            self.selection_drag_move(position, -1)
        elif self.selection_drag_mode == 0:
            self.new_current_position.emit(position)        

    def mousePressEvent(self, event):
        position = int(self.rel_to_abs(event.x()))
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers == QtCore.Qt.ShiftModifier:
            self.update_selection_mask(interval=(position,position+1),value=1)
            self.selection_drag_start(position, 1)
        elif modifiers == QtCore.Qt.ControlModifier:
            self.update_selection_mask(interval=(position,position+1),value=0)
            self.selection_drag_start(position, -1)
        else:
            self.new_current_position.emit(position)

    def mouseReleaseEvent(self, event):
        self.selection_drag_end()

    def selection_drag_start(self, position, mode):
        self.selection_drag_mode = mode
        self.selection_drag_initial_position = position

    def selection_drag_end(self):
        self.selection_drag_mode = 0
        self.selection_drag_initial_position = None

    def selection_drag_move(self, position, mode):
        if self.selection_drag_mode == mode:
            s,e = sorted([self.selection_drag_initial_position,position])
            self.update_selection_mask(interval=(s,e), value=max(mode,0))

    def rel_to_abs(self,r):
        return r/self.width()*(self.current_range[1]-self.current_range[0])+self.current_range[0]

    def abs_to_rel(self,a):
        return (a-self.current_range[0])/(self.current_range[1]-self.current_range[0])*self.width()

    def update_current_range(self, new_range=None):
        if new_range is not None: self.current_range = new_range
        for child in self.tracks+[self.overlay]: 
            child.current_range = self.current_range
            child.update()

    def update_current_position(self, position):
        self.overlay.vlines['cursor']['position'] = position
        self.overlay.update()


    def update_selection_mask(self, interval=(0,0), value=0):
        if interval[0]-self.bounds[0] < 0: return
        self.selection_mask[interval[0]-self.bounds[0]:interval[1]-self.bounds[0]] = value 
        self.overlay.set_selection_intervals(self.selection_mask, self.bounds)
        self.overlay.update()

    def update_all(self):
        self.update_current_range()
        self.update_selection_mask()
        self.overlay.update()


