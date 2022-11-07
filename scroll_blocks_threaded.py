# Module for plotting data (averages) collected from PS4824a in block mode with trigger


import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
from ps4824a_wrapper_blockmode_utils import Picoscope
import sys

my_picoscope = Picoscope(0, verbose=True)
my_picoscope.setup_channel('A',channel_range_mv=2000)
my_picoscope.setup_channel('B',channel_range_mv=2000)
my_picoscope.setup_block(block_size=100, block_duration=1e-4, pre_trigger_percent=0)
my_picoscope.setup_trigger('B',trigger_threshold_mv=1500)

data = np.empty(100)
ptr = 0

class PicoWorker(QtCore.QObject):
    triggered = QtCore.pyqtSignal()
    def pico_run(self):
        """
        Worker function that arms the trigger on PS4824a to prepare for data acquisition. 
        This function should always be called with multithreading to prevent the long wait time between
        successive triggers from freezing the GUI.
        """
        global my_picoscope, data, ptr
        while True:
            my_picoscope.run_block()
            buffers = my_picoscope.get_block_traces()
            traces_value = [val for val in buffers.values()]
            traces_mean, traces_std = np.mean(traces_value, axis = 1), np.std(traces_value, axis = 1)
            data[ptr] = traces_mean[0]
            ptr += 1
            if ptr >= data.shape[0]:
                tmp = data
                data = np.empty(data.shape[0] * 2)
                data[:tmp.shape[0]] = tmp
            self.triggered.emit()

        
class PicoTrace(pg.GraphicsLayoutWidget):
    def __init__(self):
        super().__init__()
        self.setup_gui()
        self.update_trace()
    
    def setup_gui(self):
        pg.setConfigOptions(antialias=True)
        self.resize(1920,400)
        self.setWindowTitle('PS4824a Block Mode with Trigger')

        self.panel1 = self.addPlot(title='Channel 1')
        self.panel1.setDownsampling(mode='peak')
        self.panel1.setClipToView(True)
        self.curve1 = self.panel1.plot(pen='w', symbolBrush='r', symbolPen='w')
        
    def update_trace(self):
        self.thread = QtCore.QThread()
        self.worker = PicoWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.pico_run)
        self.worker.triggered.connect(lambda: self.curve1.setData(data[:ptr]))
        self.thread.start()      

app = QtGui.QApplication(sys.argv)
win = PicoTrace()
win.show()
sys.exit(app.exec())











