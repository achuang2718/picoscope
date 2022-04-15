# adapted from ps4000aStreamingExample.py
# see also
# https://www.picotech.com/download/manuals/picoscope-4000-series-a-api-programmers-guide.pdf

import ctypes
import numpy as np
from picosdk.ps4000a import ps4000a as ps
from picosdk.functions import adc2mV, assert_pico_ok
import time
import matplotlib.pyplot as plt
from multiprocessing import Process


class Picoscope:
    def __init__(self, handle, verbose=False):
        """
        Args:
            - handle: unique int to identify each picoscope connected to the PC
        """
        self.verbose = verbose
        # Create c_handle and status ready for use
        self.c_handle = ctypes.c_int16(handle)
        # Open PicoScope 2000 Series device
        # Returns handle to c_handle for use in future API functions
        status = ps.ps4000aOpenUnit(ctypes.byref(self.c_handle), None)
        try:
            assert_pico_ok(status)
        except Exception as e:
            powerStatus = status
            if powerStatus == 286:
                status = ps.ps4000aChangePowerSource(
                    self.c_handle, powerStatus)
            else:
                raise e
            assert_pico_ok(status)
        self.intermediate_buffers = {}
        self.channel_ranges = {}
        self._set_buffer_len()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_traceback):
        try:
            status = ps.ps4000aCloseUnit(self.c_handle)
            assert_pico_ok(status)
            if self.verbose:
                print('scope closed.')
        except Exception as e:
            if self.verbose:
                print('Picoscope was not closed successfully.')
            raise e

    def _set_buffer_len(self, buffer_len=512, num_buffers=8):
        self.buffer_len = buffer_len
        self.num_buffers = num_buffers
        self.total_buffer_len = buffer_len * num_buffers

    def setup_channel(self, channel_name, analog_offset=0., channel_range=9,
                      coupling_DC=True):
        """
        Args:
            - channel_name: str (single capital letter, A-H, e.g. 'D')
            - analog_offset:
            - channel_range:
            - coupling_DC: bool, set to False for AC coupling
        """
        if self.verbose:
            print('Opening channel ' + channel_name + '...\n')
        status = ps.ps4000aSetChannel(self.c_handle,
                                      ps.PS4000A_CHANNEL['PS4000A_CHANNEL_' +
                                                         channel_name],
                                      1,
                                      coupling_DC,
                                      channel_range,
                                      analog_offset)
        assert_pico_ok(status)

        # Create buffers ready for assigning pointers for data collection
        self.intermediate_buffers[channel_name] = np.zeros(
            shape=self.buffer_len, dtype=np.int16)
        self.channel_ranges[channel_name] = channel_range
        # Set data buffer location for data collection from channel A
        # handle = chandle
        # source = PS4000A_CHANNEL_A = 0
        # pointer to buffer max = ctypes.byref(bufferAMax)
        # pointer to buffer min = ctypes.byref(bufferAMin)
        # buffer length = maxSamples
        # segment index = 0
        # ratio mode = PS4000A_RATIO_MODE_NONE = 0
        status = ps.ps4000aSetDataBuffers(self.c_handle,
                                          ps.PS4000A_CHANNEL['PS4000A_CHANNEL_' +
                                                             channel_name],
                                          self.intermediate_buffers[channel_name].ctypes.data_as(
                                              ctypes.POINTER(ctypes.c_int16)),
                                          None,
                                          self.buffer_len,
                                          0,
                                          ps.PS4000A_RATIO_MODE['PS4000A_RATIO_MODE_NONE'])
        assert_pico_ok(status)

    def setup_stream(self, sample_interval):
        """
        Args:
            - sample_interval: int, in microseconds

        """
        sampleInterval = ctypes.c_int32(sample_interval)
        sampleUnits = ps.PS4000A_TIME_UNITS['PS4000A_US']
        # We are not triggering:
        maxPreTriggerSamples = 0
        autoStopOn = 1
        # No downsampling:
        downsampleRatio = 1
        status = ps.ps4000aRunStreaming(self.c_handle,
                                        ctypes.byref(
                                            sampleInterval),
                                        sampleUnits,
                                        maxPreTriggerSamples,
                                        self.total_buffer_len,
                                        autoStopOn,
                                        downsampleRatio,
                                        ps.PS4000A_RATIO_MODE['PS4000A_RATIO_MODE_NONE'],
                                        self.buffer_len)
        assert_pico_ok(status)
        self.sample_interval, self.sample_interval_unit = sample_interval, 'us'

    def stream_traces(self):
        self.complete_buffers = {key: np.zeros(shape=self.total_buffer_len, dtype=np.int16)
                                 for key in self.intermediate_buffers}
        self._nextSample = 0
        self._autoStopOuter = False
        self._wasCalledBack = False

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt,
                               triggered, autoStop, param):
            """
            GetStreamingLatestValues requires a callback function which takes the above
            as args.
            """
            self._wasCalledBack = True
            destEnd = self._nextSample + noOfSamples
            sourceEnd = startIndex + noOfSamples
            for chl, buffer in self.complete_buffers.items():
                buffer[self._nextSample:destEnd] = self.intermediate_buffers[chl][startIndex:sourceEnd]
            self._nextSample += noOfSamples
            if autoStop:
                self._autoStopOuter = True

        # Convert the python function into a C function pointer.
        cFuncPtr = ps.StreamingReadyType(streaming_callback)
        while self._nextSample < self.total_buffer_len and not self._autoStopOuter:
            self._wasCalledBack = False
            ps.ps4000aGetStreamingLatestValues(self.c_handle, cFuncPtr, None)
            if not self._wasCalledBack:
                # If we weren't called back by the driver, this means no data is ready.
                time.sleep(0.01)

        def convert_ADC_units():
            # Find maximum ADC count value
            # handle = chandle
            # pointer to value = ctypes.byref(maxADC)
            maxADC = ctypes.c_int16()
            status = ps.ps4000aMaximumValue(
                self.c_handle, ctypes.byref(maxADC))
            assert_pico_ok(status)
            # Convert ADC counts data to mV
            self.complete_buffers = {chl: adc2mV(buffer, self.channel_ranges[chl], maxADC) for
                                     chl, buffer in self.complete_buffers.items()}
            self.voltage_unit = 'mV'

        convert_ADC_units()
        return self.complete_buffers


def main():
    my_picoscope = Picoscope(0)

    def get_stream(my_picoscope):
        my_picoscope.setup_stream(sample_interval=250)
        buffers = my_picoscope.stream_traces()
        return buffers

    def stream_to_file(f, buffers):
        print('writing')
        for key, val in buffers.items():
            np.savetxt(f, np.array(val), delimiter=',')

    with my_picoscope:
        with open('pico.csv', 'a') as f:
            my_picoscope.setup_channel('A')
            for _ in range(5):
                my_picoscope.setup_stream(sample_interval=250)
                buffers = my_picoscope.stream_traces()
                print(np.mean(buffers['A']))
                file_write_thread = Process(
                    target=stream_to_file, args=(f, buffers,))
                file_write_thread.start()
    file_write_thread.join()
    my_arr = np.loadtxt('pico.csv', delimiter=',')
    plt.plot(my_arr)
    plt.show()


if __name__ == '__main__':
    main()
