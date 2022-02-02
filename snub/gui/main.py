from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import sys, os, cv2, json
import numpy as np
from functools import partial
from snub.gui.utils import SelectionIntervals
from snub.gui.stacks import PanelStack, TrackStack




def set_style(app):
    # https://www.wenzhaodesign.com/devblog/python-pyside2-simple-dark-theme
    # button from here https://github.com/persepolisdm/persepolis/blob/master/persepolis/gui/palettes.py
    app.setStyle(QStyleFactory.create("Fusion"))

    darktheme = QPalette()
    darktheme.setColor(QPalette.Window, QColor(45, 45, 45))
    darktheme.setColor(QPalette.WindowText, QColor(222, 222, 222))
    darktheme.setColor(QPalette.Button, QColor(45, 45, 45))
    darktheme.setColor(QPalette.ButtonText, QColor(222, 222, 222))
    darktheme.setColor(QPalette.AlternateBase, QColor(222, 222, 222))
    # darktheme.setColor(QPalette.AlternateBase, QColor(0, 222, 0))
    darktheme.setColor(QPalette.ToolTipBase, QColor(222, 222, 222))
    darktheme.setColor(QPalette.Highlight, QColor(45, 45, 45))
    darktheme.setColor(QPalette.Disabled, QPalette.Light, QColor(60, 60, 60))
    darktheme.setColor(QPalette.Disabled, QPalette.Shadow, QColor(50, 50, 50))
    darktheme.setColor(QPalette.Disabled, QPalette.ButtonText,
                       QColor(111, 111, 111))
    darktheme.setColor(QPalette.Disabled, QPalette.Text, QColor(122, 118, 113))
    darktheme.setColor(QPalette.Disabled, QPalette.WindowText,
                       QColor(122, 118, 113))
    darktheme.setColor(QPalette.Disabled, QPalette.Base, QColor(32, 32, 32))
    app.setPalette(darktheme)
    return app




class Slider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            x = e.pos().x()
            value = (self.maximum() - self.minimum()) * x / self.width() + self.minimum()
            self.setValue(np.around(value))
        else:
            return super().mousePressEvent(self, e)




class ProjectTab(QWidget):
    new_current_position = pyqtSignal(int)

    def __init__(self, project_directory):
        super().__init__()
        # load config
        self.project_directory = project_directory
        config_path = os.path.join(self.project_directory,'config.json')
        config = json.load(open(config_path,'r'))
        config,error_messages = self.validate_and_autofill_config(config)
        if len(error_messages) > 0: 
            self.config_error(config_path, error_messages)
            return
            #self.close_tab()
  
        # initialize state variables
        self.playing = False
        self.bounds = config['bounds']
        self.layout = config['layout']
        self.current_time = config['current_time']
        self.play_speed = config['initial_playspeed']
        self.animation_step = config['animation_step']

        # keep track of current selection
        self.selected_intervals = SelectionIntervals(timestep=config['timestep'])
        
        # create major gui elements
        self.panelStack = PanelStack(config, self.selected_intervals, **config['panel_props'])
        self.trackStack = TrackStack(config, self.selected_intervals, **config['track_props'])

        # timer for live play
        self.timer = QTimer(self)

        # controls along bottom row
        self.play_button = QPushButton()
        self.speed_slider = Slider(Qt.Horizontal)
        self.speed_label = QLabel()
        self.deselect_button = QPushButton('Deselect All')

        # connect signals and slots
        self.deselect_button.clicked.connect(self.deselect_all)
        self.speed_slider.valueChanged.connect(self.change_play_speed)
        self.play_button.clicked.connect(self.toggle_play_state)
        self.trackStack.new_current_time.connect(self.update_current_time)
        self.trackStack.selection_change.connect(self.update_selected_intervals)
        for panel in self.panelStack.panels: 
            panel.new_current_time.connect(self.update_current_time)
            panel.selection_change.connect(self.update_selected_intervals)
        self.timer.timeout.connect(self.increment_current_time)

        # initialize layout
        self.initUI()
        self.trackStack.update_current_range()
        self.update_current_time(self.current_time)


    def initUI(self):
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.panelStack)
        self.splitter.addWidget(self.trackStack)

        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.speed_label.setText('{}X'.format(self.play_speed))
        self.speed_label.setMinimumWidth(35)
        self.speed_slider.setMinimum(0)
        self.speed_slider.setMaximum(7)
        self.speed_slider.setValue(0)
        self.speed_slider.setTickPosition(QSlider.TicksBothSides)
        self.speed_slider.setTickInterval(1)
        self.speed_slider.setMaximumWidth(150)
        self.deselect_button.setMaximumWidth(100)

        buttons = QHBoxLayout()
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.speed_label)
        buttons.addWidget(self.speed_slider)
        buttons.addStretch(0)
        buttons.addWidget(self.deselect_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter)
        layout.addLayout(buttons)


    def validate_and_autofill_config(self,config):
        error_messages = []
        for k in ['bounds']:
            if not k in config:
                error_messages.append('config is missing the key "{}"'.format(k))

        config['project_directory'] = self.project_directory
        if not 'layout' in config: config['layout'] = 'columns'
        if not 'timestep' in config: config['timestep'] = 1/30
        if not 'current_time' in config: config['current_time'] = 0
        if not 'initial_playspeed' in config: config['initial_playspeed'] = 1
        if not 'animation_step' in config: config['animation_step'] = 1/30
        if not 'track_props' in config: config['track_props'] = {}
        if not 'panel_props' in config: config['panel_props'] = {}
        if not 'spike_rasters' in config: config['spike_rasters'] = []
        if not 'scatters' in config: config['scatters'] = []
        if not 'rasters' in config: config['rasters'] = []
        if not 'videos' in config: config['videos'] = []
        if not 'meshes' in config: config['meshes'] = []
        if not 'vlines' in config: config['vlines'] = {}

        for widget_name, requred_keys in {
            'rasters': ['data_path', 'binsize'],
            'videos': ['video_path', 'timestamps_path'],
            'meshes': ['data_path', 'faces_path', 'timestamps_path']
        }.items():
            for props in config[widget_name]:
                for k in requred_keys:
                    if not k in props:
                        error_messages.append('{} is missing the key "{}"'.format(widget_name,k))

        return config, error_messages


    def config_error(self, config_path, error_messages):
        title = QLabel('The following config file is incomplete')
        path = QLabel('   '+config_path)
        errors = QLabel('<html><ul><li>'+'</li><li>'.join(error_messages)+'</li></ul></html>')

        title.setFont(QFont( "Arial", 24, QFont.Bold))
        font = QFont( "Arial", 16)
        font.setItalic(True)
        path.setFont(font)
        errors.setFont(QFont( "Arial", 18))

        text_layout = QVBoxLayout()
        text_layout.setSpacing(10)
        text_layout.addStretch(0)
        text_layout.addWidget(title)
        text_layout.addWidget(path)
        text_layout.addWidget(errors)
        text_layout.addStretch(0)
        layout = QHBoxLayout(self)
        layout.addStretch(0)
        layout.addLayout(text_layout); 
        layout.addStretch(0)


    def change_layout(self, name):
        self.splitter.setOrientation({'columns':Qt.Horizontal, 'rows':Qt.Vertical}[name])
        self.panelStack.splitter.setOrientation({'columns':Qt.Vertical, 'rows':Qt.Horizontal}[name])

    def change_play_speed(self, log2_speed):
        self.play_speed = int(2**log2_speed)
        self.speed_label.setText('{}X'.format(self.play_speed))

    def deselect_all(self):
        self.update_selected_intervals([self.bounds], [False])

    def update_selected_intervals(self, intervals, is_selected):
        for (start,end),sel in zip(intervals, is_selected):
            if sel: self.selected_intervals.add_interval(start,end)
            else: self.selected_intervals.remove_interval(start,end)
        self.trackStack.update_selected_intervals()
        self.panelStack.update_selected_intervals()

    def update_current_time(self,current_time):
        self.current_time = current_time
        self.trackStack.update_current_time(current_time)
        self.panelStack.update_current_time(current_time)

    def increment_current_time(self):
        new_time = self.current_time + self.play_speed*self.animation_step
        if new_time >= self.bounds[1]:
            new_time = self.bounds[0]
        self.update_current_time(new_time)

    def toggle_play_state(self):
        if self.playing: self.pause()
        else: self.play()

    def play(self):
        self.timer.start(1000*self.animation_step)
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        self.playing = True

    def pause(self):
        self.timer.stop()
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.playing = False


class MainWindow(QMainWindow):
    '''
    Main window that contains menu bar and tab widget. Contains methods for
    opening, reloading, and closing project tabs.
    '''
    def __init__(self, args):
        super().__init__()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.setCentralWidget(self.tabs)
        self.setWindowTitle('Systems Neuro Browser')

        open_project = QAction("&Open Project", self)
        open_project.setShortcut("Ctrl+O")
        open_project.triggered.connect(self.file_open)

        reload_data = QAction("&Reload Data", self)
        reload_data.setShortcut("Ctrl+R")
        reload_data.triggered.connect(self.file_reload)

        save_layout = QAction("&Layout", self)
        save_layout.triggered.connect(self.file_save_layout)

        self.set_layout_to_rows = QAction("&Rows", self)
        self.set_layout_to_cols = QAction("&Columns", self)
        self.set_layout_to_rows.setCheckable(True)
        self.set_layout_to_cols.setCheckable(True)
        self.set_layout_to_rows.triggered.connect(partial(self.change_layout,'rows'))
        self.set_layout_to_cols.triggered.connect(partial(self.change_layout,'columns'))

        mainMenu = self.menuBar()
        mainMenu.setNativeMenuBar(False)

        fileMenu = mainMenu.addMenu('&File')
        fileMenu.addAction(open_project)
        fileMenu.addAction(reload_data)

        #saveMenu = fileMenu.addMenu('&Save...')
        #saveMenu.addAction(save_layout)

        windowMenu = mainMenu.addMenu('&Window')
        layoutMenu = windowMenu.addMenu('&Layout...')
        layoutMenu.addAction(self.set_layout_to_cols)
        layoutMenu.addAction(self.set_layout_to_rows)


        # try to open projects that are passed as command line arguments
        for a in args:
            if os.path.exists(a): 
                self.open_project(a)



    def change_layout(self, name):
        current_tab = self.tabs.currentWidget()
        current_tab.change_layout(name)
        self.set_layout_to_cols.setChecked(name == 'columns')
        self.set_layout_to_rows.setChecked(name == 'rows')


    def tab_changed(self, i):
        if i >= 0:
            current_tab = self.tabs.widget(i)
            self.set_layout_to_cols.setChecked(current_tab.layout == 'columns')
            self.set_layout_to_rows.setChecked(current_tab.layout == 'rows')

    # close tab triggered when user clicks "X" on the tab
    def close_tab(self, i):
        self.tabs.removeTab(i)

    # triggered when user clicks "Open Project" in the "File" menu.
    # multiple project directories can be selected at once
    def file_open(self):
        project_directories = self.getExistingDirectories()
        error_directories = []
        for project_dir in project_directories:
            if len(project_dir)>0:
                if os.path.exists(os.path.join(project_dir,'config.json')):
                    self.open_project(project_dir)
                else: error_directories.append(project_dir)
        if len(error_directories) > 0:
            QMessageBox.about(self, '', '\n\n'.join(
                ['The following directories lack a config file.']+error_directories))

    # triggered when user clicks "Reload Data" in the "File" menu
    def file_reload(self):
        current_index = self.tabs.currentIndex()
        current_tab = self.tabs.currentWidget()
        project_dir = current_tab.project_directory
        self.close_tab(current_index)
        self.open_project(project_dir)

    # triggered when user clicks "Layout" in the "File > Save..." menu
    def file_save_layout(self):
        print('save')

    # open the project contained in project_directory
    def open_project(self, project_directory):
        name = project_directory.strip(os.path.sep).split(os.path.sep)[-1]
        project_tab = ProjectTab(project_directory)
        self.tabs.addTab(project_tab, name)
        self.tabs.setCurrentWidget(project_tab)

    def getExistingDirectories(self):
        """
        Workaround for selecting multiple directories
        adopted from http://www.qtcentre.org/threads/34226-QFileDialog-select-multiple-directories?p=158482#post158482
        This also give control about hidden folders
        """
        dlg = QFileDialog(self)
        dlg.setOption(dlg.DontUseNativeDialog, True)
        dlg.setOption(dlg.HideNameFilterDetails, True)
        dlg.setFileMode(dlg.Directory)
        dlg.setOption(dlg.ShowDirsOnly, True)
        dlg.findChildren(QListView)[0].setSelectionMode(QAbstractItemView.ExtendedSelection)
        dlg.findChildren(QTreeView)[0].setSelectionMode(QAbstractItemView.ExtendedSelection)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.selectedFiles()
        return [str(), ]


def run():
    app = QApplication(sys.argv)
    app = set_style(app)
    icon_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'icons','app_icon.png')
    app.setWindowIcon(QIcon(icon_path))

    window = MainWindow(sys.argv[1:])
    window.resize(1500, 900)

    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    run()




