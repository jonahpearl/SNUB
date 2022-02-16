from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import pyqtgraph as pg
import numpy as np
import time
import os
import cmapy
from functools import partial

from vispy.scene import SceneCanvas
from vispy.scene.visuals import Markers, Rectangle
from vispy.util import keys

from snub.gui.panels import Panel
from snub.gui.utils import HeaderMixin, AdjustColormapDialog, IntervalIndex



class SelectionRectangle(pg.GraphicsObject):
    def __init__(self, topLeft=(0,0), size=(0,0)):
        pg.GraphicsObject.__init__(self)
        self.topLeft = topLeft
        self.size = size
        self.generatePicture()

    def generatePicture(self):
        self.picture = QPicture()
        p = QPainter(self.picture)
        p.setPen(pg.mkPen('w'))
        p.setBrush(pg.mkBrush((255,255,255,50)))
        tl = QPointF(self.topLeft[0], self.topLeft[1])
        size = QSizeF(self.size[0], self.size[1])
        p.drawRect(QRectF(tl, size))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def update_location(self, topLeft, size):
        self.topLeft = topLeft
        self.size = size
        self.generatePicture()

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())



class ScrubbableViewBox(pg.ViewBox):
    drag_event = pyqtSignal(object, Qt.Modifier)
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def mouseDragEvent(self, event):
        event.accept()
        modifiers = QApplication.keyboardModifiers()
        self.drag_event.emit(event, modifiers)
        if not modifiers in [Qt.ShiftModifier,Qt.ControlModifier]:
            pg.ViewBox.mouseDragEvent(self, event)




############################################
# THIS IS A CONTSTRUCTION SITE MOVING TO VISPY
 
class ScatterPanel(Panel, HeaderMixin):
    eps = 1e-10

    def __init__(self, config, selected_intervals, data_path=None, name='',
                 pointsize=10, linewidth=1, facecolor=(180,180,180), xlim=None, ylim=None, 
                 selected_edgecolor=(255,255,0), edgecolor=(0,0,0), current_node_size=20, 
                 current_node_color=(255,0,0), colormap='viridis',
                 selection_intersection_threshold=0.5, feature_labels=[], **kwargs):

        super().__init__(config, **kwargs)
        assert data_path is not None
        self.selected_intervals = selected_intervals
        self.bounds = config['bounds']
        self.min_step = config['min_step']
        self.pointsize = pointsize
        self.linewidth = linewidth
        self.facecolor = np.array(facecolor)/256
        self.edgecolor = np.array(edgecolor)/256
        self.colormap = colormap
        self.selected_edgecolor = np.array(selected_edgecolor)/256
        self.current_node_size = current_node_size
        self.current_node_color = np.array(current_node_color)/256
        self.selection_intersection_threshold = selection_intersection_threshold
        self.feature_labels = ['Interval start','Interval end']+feature_labels
        self.vmin,self.vmax = 0,1
        self.current_feature_label = '(No color)'        

        self.data = np.load(os.path.join(config['project_directory'],data_path))
        self.data[:,2:4] = self.data[:,2:4] + np.array([-self.eps, self.eps])
        self.is_selected = np.zeros(self.data.shape[0])>0
        self.plot_order = np.arange(self.data.shape[0])
        self.interval_index = IntervalIndex(min_step=self.min_step, intervals=self.data[:,2:4])
        self.adjust_colormap_dialog = AdjustColormapDialog(self, self.vmin, self.vmax)

        self.canvas = SceneCanvas(self, keys='interactive', show=True)
        self.canvas.events.mouse_move.connect(self.mouse_move)
        self.canvas.events.mouse_release.connect(self.mouse_release)
        self.viewbox = self.canvas.central_widget.add_grid().add_view(row=0, col=0, camera='panzoom')
        self.viewbox.camera.aspect=1
        self.scatter = Markers(antialias=0)
        self.scatter_selected = Markers(antialias=0)
        self.current_node_marker = Markers(antialias=0)
        self.rect = Rectangle(border_color=(1,1,1), color=(1,1,1,.2), center=(0,0), width=1, height=1)
        self.viewbox.add(self.scatter)
        self.initUI(name=name, xlim=xlim, ylim=ylim)

    def initUI(self, xlim=None, ylim=None, **kwargs):
        super().initUI(**kwargs)
        self.layout.addWidget(self.canvas.native, 1)
        self.update_scatter()
        if xlim is None: xlim = [self.data[:,0].min(),self.data[:,0].max()]
        if ylim is None: ylim = [self.data[:,1].min(),self.data[:,1].max()]
        self.viewbox.camera.set_range(x=xlim, y=ylim, margin=0.1)
        self.rect.order = 0
        self.current_node_marker.order=1
        self.scatter_selected.order=2
        self.scatter.order=3
        

    def update_scatter(self):
        pos = self.data[self.plot_order,:2]
        if self.current_feature_label in self.feature_labels:
            x = self.data[self.plot_order,2+self.feature_labels.index(self.current_feature_label)]
            x = np.clip((x - self.vmin) / (self.vmax - self.vmin), 0, 1)
            face_color = cmapy.cmap(self.colormap).squeeze()[:,::-1][(255*x).astype(int)]/255
        else: face_color = np.repeat(self.facecolor[None],self.data.shape[0],axis=0)

        self.scatter.set_data(
            pos=pos, 
            face_color=face_color,
            edge_color=self.edgecolor, 
            edge_width=self.linewidth, 
            size=self.pointsize)

        if self.is_selected.any():
            is_selected = self.is_selected[self.plot_order]
            self.scatter_selected.set_data(
                pos=pos[is_selected],
                face_color=face_color[is_selected],
                edge_color=self.selected_edgecolor, 
                edge_width=(self.linewidth*2), 
                size=self.pointsize)
            self.scatter_selected.parent = self.viewbox.scene
        else: self.scatter_selected.parent = None


    def update_current_time(self, t):
        current_nodes = self.interval_index.intervals_containing(np.array([t]))
        current_nodes = current_nodes[np.all([
            self.data[current_nodes][:,2]<=t, 
            self.data[current_nodes][:,3]>=t],axis=0)]
        if len(current_nodes)>0:
            self.current_node_marker.set_data(
                pos=self.data[current_nodes,:2],
                face_color=self.current_node_color,
                size=self.current_node_size)
            self.current_node_marker.parent = self.viewbox.scene
        else: self.current_node_marker.parent = None


    def context_menu(self, event):
        menu_options = [('Adjust colormap range', self.show_adjust_colormap_dialog),
                        ('Sort by color value', self.sort_by_color_value),
                        ('Restore original order', self.sort_original)]

        contextMenu = QMenu(self)
        for name,slot in menu_options:
            label = QLabel(name)
            action = QWidgetAction(self)
            action.setDefaultWidget(label)
            action.triggered.connect(slot)
            contextMenu.addAction(action)

        colorby = QMenu('Color by...', contextMenu)
        for name in self.feature_labels+['(No color)']:
            label = QLabel(name)
            action = QWidgetAction(self)
            action.setDefaultWidget(label)
            action.triggered.connect(partial(self.colorby,name))
            colorby.addAction(action)

        contextMenu.addMenu(colorby)
        contextMenu.setStyleSheet("""
            QWidget { background-color : #3E3E3E; }
            QMenu::item, QLabel { background-color : #3E3E3E; padding: 5px 6px 5px 6px;}
            QMenu::item:selected, QLabel:hover { background-color: #999999;} """)
        action = contextMenu.exec_(event.native.globalPos())


    def update_colormap_range(self, vmin, vmax):
        self.vmin,self.vmax = vmin,vmax
        self.update_scatter()

    def sort_original(self):
        self.plot_order = np.arange(self.data.shape[0])
        self.update_scatter()

    def sort_by_color_value(self):
        label = self.current_feature_label
        if label in self.feature_labels:
            x = self.data[:,2+self.feature_labels.index(label)]
            self.plot_order = np.argsort(-x)
            self.update_scatter()

    def show_adjust_colormap_dialog(self):
        self.adjust_colormap_dialog.show()

    def colorby(self, label):
        self.current_feature_label = label
        if label in self.feature_labels:
            x = self.data[:,2+self.feature_labels.index(label)]
            self.vmin,self.vmax = x.min(),x.max()
            self.adjust_colormap_dialog.update_range(self.vmin,self.vmax)
        self.update_scatter()

    def mouse_release(self, event):
        self.rect.parent = None
        if event.button == 2: 
            self.context_menu(event)

    def mouse_move(self, event):
        if event.is_dragging:
            mods = event.modifiers
            if keys.SHIFT in mods or keys.CONTROL in mods:
                current_pos = self.viewbox.scene.transform.imap(event.pos)[:2]
                start_pos = self.viewbox.scene.transform.imap(event.press_event.pos)[:2]
                if all((current_pos-start_pos)!=0):
                    self.rect.center = (current_pos+start_pos)/2
                    self.rect.width = np.abs(current_pos[0]-start_pos[0])
                    self.rect.height = np.abs(current_pos[1]-start_pos[1])
                    self.rect.parent = self.viewbox.scene

                selection_value = int(mods[0]==keys.SHIFT)
                enclosed_points = np.all([
                    self.data[:,:2]>=np.minimum(current_pos, start_pos), 
                    self.data[:,:2]<=np.maximum(current_pos, start_pos)],axis=(0,2))
                self.selection_change.emit(
                    list(self.data[enclosed_points,2:4]), 
                    [selection_value]*len(enclosed_points))

    def update_selected_intervals(self):
        intersections = self.selected_intervals.intersection_proportions(self.data[:,2:4])
        self.is_selected = intersections > self.selection_intersection_threshold
        self.update_scatter()


