# Module for plotting mock data (averages) collected from PS4824a in block mode with trigger

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
import sys
import time

#Simulate data acquisition on two channels
data = np.empty((100,2))
ptr = 0


class PicoWorker(QtCore.QObject):
    triggered = QtCore.pyqtSignal()
    def pico_run(self):
        """
        Worker function that arms the trigger on PS4824a to prepare for data acquisition. 
        This function should always be called with multithreading to prevent the long wait time between
        successive triggers from freezing the GUI.
        """
        global data, ptr
        while True:
            time.sleep(0.5) #simulate long wait times between scope triggers
            data[ptr] = np.random.normal(size=2) 
            ptr += 1
            if ptr >= data.shape[0]:
                tmp = data
                data = np.empty((data.shape[0] * 2, 2))
                data[:tmp.shape[0]] = tmp
            self.triggered.emit() #pyqt signal to update the plot in the GUI
        
class PicoTrace(pg.GraphicsLayoutWidget):
    def __init__(self):
        super().__init__()
        self.setup_gui()
        self.update_trace()
    
    def setup_gui(self):
        pg.setConfigOptions(antialias=True)
        self.resize(1920,500)
        self.setWindowTitle('PS4824a Block Mode with Trigger')

        self.panel1 = self.addPlot(title='Channel 1')
        self.panel1.setDownsampling(mode='peak')
        self.panel1.setClipToView(True)
        self.curve1 = self.panel1.plot(pen='w', symbolBrush='r', symbolPen='w')
        
        self.nextRow()

        self.panel2 = self.addPlot(title='Channel 2')
        self.panel2.setDownsampling(mode='peak')
        self.panel2.setClipToView(True)
        self.curve2 = self.panel2.plot(pen='w', symbolBrush='b', symbolPen='w')


    def update_trace(self):
        """
        Use QThread to move picoscope onto a different thread.
        """
        self.thread = QtCore.QThread()
        self.worker = PicoWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.pico_run)
        self.worker.triggered.connect(lambda: self.curve1.setData(data[:ptr, 0]))
        self.worker.triggered.connect(lambda: self.curve2.setData(data[:ptr, 1]))
        self.thread.start()      

app = QtGui.QApplication(sys.argv)
win = PicoTrace()
win.show()
sys.exit(app.exec())











