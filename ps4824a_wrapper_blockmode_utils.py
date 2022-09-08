# adapted from ps4000aStreamingExample.py, ps4824BlockExample.py and achuang2718's ps4824a_wrapper
# see also
# https://www.picotech.com/download/manuals/picoscope-4000-series-a-api-programmers-guide.pdf

import ctypes
from math import floor, log2
import sys
import numpy as np
from picosdk.ps4000a import ps4000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
import time
import matplotlib.pyplot as plt
from multiprocessing import Process


class Picoscope:
    def __init__(self, handle, serial=None, verbose=False):
        """
        Args:
            - handle: unique int to identify each picoscope connected to the PC
            - serial: 10-digit string typically found on the back of the device between two asterisks
        """
        self.verbose = verbose
        # Create c_handle and status ready for use
        self.c_handle = ctypes.c_int16(handle)
        # If specifying a device to open by its serial number, need to convert serial number into byte array
        if serial != None:
            serial = ctypes.create_string_buffer(serial.encode('utf_8'))
        # Open PicoScope 4000 Series device
        # Returns handle to c_handle for use in future API functions
        status = ps.ps4000aOpenUnit(ctypes.byref(self.c_handle), serial)
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
        
        self.buffers = {}
        self.active_channels = []
        #channel voltage range index as defined in ps4000a.py
        self.channel_ranges = {} 
        #lookup list to convert range index to mV. Max of 50000 mV comes from datasheet.
        self.allowed_ranges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000] 

        self._get_max_ADC()

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

    def _get_max_ADC(self):
        """
        Query the maximum ADC count supported by the device which will be used in unit conversions later.
        """
        # handle = chandle
        # pointer to value = ctypes.byref(maxADC)
        self.max_ADC = ctypes.c_int16()
        status = ps.ps4000aMaximumValue(self.c_handle, ctypes.byref(self.max_ADC))
        assert_pico_ok(status)

    def setup_channel(self, channel_name, analog_offset=0, channel_range_mv=2000,
                      coupling_DC=True):
        """
        Args:
            - channel_name: str (single capital letter, A-H, e.g. 'D')
            - analog_offset: offsets the input, in Volts. Check datasheet for allowed values. TODO: coerce these things too!
            - channel_range_mv: in mV  
            - coupling_DC: bool, set to False for AC coupling
        """
        if self.verbose:
            print('Opening channel ' + channel_name + '...\n')  
        def coerce_channel_range(channel_range_mv):
            """
            Coerce channel voltage range set by user into device allowed values or raise an error

            Args: 
                - channel_range_mv: user set channel range in mV
            
            Return:
                - coerced channel range converted to a range index as defined in ps4000a.py
            """
            try:
                coerced_range = next(x for x in self.allowed_ranges if x >= abs(channel_range_mv))
                if channel_range_mv != coerced_range:
                    print(f'[PS4842a configuration error]: channel {channel_name} range setting coerced to {coerced_range} mV !\n')
            except StopIteration:
                coerced_range = self.allowed_ranges[-1]
                print((f'[PS4842a configuration error]: channel {channel_name} range setting is out of bound and therefore'
                        f' coerced to 50000 mV !\n'))
            return self.allowed_ranges.index(coerced_range) 

        channel_range = coerce_channel_range(channel_range_mv)

        # Set up a channel
        # handle = chandle
        # channel = PS4000a_CHANNEL_A = 0
        # enabled = 1
        # coupling type = PS4000a_DC = 1
        # range = PS4000a_2V = 7
        # analogOffset = 0 V
        status = ps.ps4000aSetChannel(self.c_handle,
                                      ps.PS4000A_CHANNEL['PS4000A_CHANNEL_' +
                                                         channel_name],
                                      1,
                                      coupling_DC,
                                      channel_range,
                                      analog_offset)
        assert_pico_ok(status)
        self.active_channels.append(channel_name)
        self.channel_ranges[channel_name] = channel_range

    def setup_trigger(self, source_channel_name, trigger_threshold_mv=100, 
                        trigger_direction=2, trigger_delay=0, auto_trigger=0):
        """
        Setup a single trigger on a selected source channel. Must setup the channel first!
        Args:
            - source_channel_name: str (single capital letter, A-H, e.g. 'D'). 
            - trigger_threshold_mv: in mV. 
            - trigger_direction: trigger mode (e.g. = 2 for triggering on rising edge)
            - trigger_delay: in sample periods
            - auto_trigger: waittime in ms after which the trigger will automatically
                            fire. Set to 0 to disable. 
        """
        def convert_trigger_units(trigger_threshold_mv):
            """
            Convert user input trigger threshold in mv to ADC counts
            """
            try:
                source_channel_range = self.channel_ranges[source_channel_name]
            except KeyError:
                print((f'[PS4842a configuration error]: channel {source_channel_name} not found. '
                        'Setup all channels before setting a trigger.\n \nProgram aborted.'))
                sys.exit()
            if self.allowed_ranges[source_channel_range] <= trigger_threshold_mv:
                print('[PS4842a configuration error]: trigger threshold is higher than the channel range.\n',
                        'Program aborted.')
                sys.exit()
            return mV2adc(trigger_threshold_mv, source_channel_range, self.max_ADC)
        
        trigger_threshold = convert_trigger_units(trigger_threshold_mv)
        # Set up single trigger
        # handle = chandle
        # enabled = 1
        # source = PS4000a_CHANNEL_A = 0
        # threshold = 1024 ADC counts
        # direction = PS4000a_RISING = 2
        # delay = 0 s
        # auto Trigger = 1000 ms           
        status = ps.ps4000aSetSimpleTrigger(self.c_handle,
                                            1,
                                            ps.PS4000A_CHANNEL['PS4000A_CHANNEL_' +
                                                                source_channel_name],
                                            trigger_threshold,
                                            trigger_direction,
                                            trigger_delay,
                                            auto_trigger)
        assert_pico_ok(status)

        if self.verbose:
            print(f'Trigger is armed on channel {source_channel_name}. Waiting for the first data trace...\n')

    def setup_block(self, block_size=1000, block_duration=1, pre_trigger_percent=0):
        """
        Setup the the size and duration of the data block one wish to capture.
        Args: 
            - block_size: number of samples to take in each block
            - block_duration: in seconds
            - pre_trigger_percent: percentage of the sample took before trigger event (from 0 to 1)
        """
        def convert_timebase(block_size, block_duration):
            """
            Convert sampling rate defined by user (by specifying block duration and size) to a timebase integer 
            that the device uses to configure the clock (see device documentation). Additionally coerces the rate to 1000kS/s
            if setting is out of bound.
            """
            sampling_rate = (block_size-1) / block_duration # in Samples /s
            timebase = floor(400e6 / sampling_rate)-1 # see documentation for definition
            if 0 <= timebase <= 2e32 - 1:
                print((f'Configured PS4824a to take blocks of {block_size} samples at {sampling_rate*1e-3:.3f} kS/s,'
                f'each lasting {(block_size-1)/sampling_rate:.3f} s\n'))
            else:
                print((f'[PS4842a configuration error]: sampling rate of {sampling_rate*1e-3:.3f} kS/s is out of bound.\n'
                        f'Coerced to taking blocks of {block_size} samples at 100 kS/s, each lasting'
                        f'{(block_size-1)/100e3:.3f} s\n'))
                timebase = 3999
            return timebase
        
        self.timebase = convert_timebase(block_size,block_duration)
        self.block_size = block_size
        self.pre_trigger_samples = floor(block_size * pre_trigger_percent)
        self.post_trigger_samples = block_size - self.pre_trigger_samples
        # i don't know what the following arguments do
        time_interval_ns = ctypes.c_float()
        returned_block_size = ctypes.c_int32() 

        # Get timebase information
        # WARNING: When using this example it may not be possible to access all Timebases as all channels are enabled by default when opening the scope.  
        # To access these Timebases, set any unused analogue channels to off.
        # handle = chandle
        # timebase = 8 = timebase
        # noSamples = maxSamples
        # pointer to timeIntervalNanoseconds = ctypes.byref(timeIntervalns)
        # pointer to maxSamples = ctypes.byref(returnedMaxSamples)
        # segment index = 0
        status = ps.ps4000aGetTimebase2(self.c_handle, 
                                        self.timebase, 
                                        self.block_size, 
                                        ctypes.byref(time_interval_ns), 
                                        ctypes.byref(returned_block_size), 
                                        0)
        assert_pico_ok(status)


    def run_block(self):
        """
        Call this function after the device is configured to prepare fresh buffers for capturing a new data block, and to start this capture
        """
        # Create buffers ready for assigning pointers for data collection
        # Set data buffer location for data collection from channel_name 
        # handle = chandle
        # source = PS4000A_CHANNEL_A = 0
        # pointer to buffer max = ctypes.byref(bufferAMax)
        # pointer to buffer min = ctypes.byref(bufferAMin)
        # buffer length = maxSamples
        # segment index = 0
        # ratio mode = PS4000A_RATIO_MODE_NONE = 0
        for channel in self.active_channels:
            self.buffers[channel] = (ctypes.c_int16 * self.block_size)()
            status = ps.ps4000aSetDataBuffers(self.c_handle,
                                            ps.PS4000A_CHANNEL['PS4000A_CHANNEL_' +
                                                                channel],
                                            ctypes.byref(self.buffers[channel]),
                                            None,
                                            self.block_size,
                                            0,
                                            ps.PS4000A_RATIO_MODE['PS4000A_RATIO_MODE_NONE'])
        assert_pico_ok(status)
        # Run block capture
        # handle = chandle
        # number of pre-trigger samples = preTriggerSamples
        # number of post-trigger samples = PostTriggerSamples
        # timebase = 3 = 80 ns = timebase (see Programmer's guide for mre information on timebases)
        # time indisposed ms = None (not needed in the example)
        # segment index = 0
        # lpReady = None (using ps4000aIsReady rather than ps4000aBlockReady)
        # pParameter = None
        status = ps.ps4000aRunBlock(self.c_handle,
                                    self.pre_trigger_samples,
                                    self.post_trigger_samples,
                                    self.timebase,
                                    None,
                                    0,
                                    None,
                                    None)
        assert_pico_ok(status)

    def get_block_traces(self):
        """
        Check and transfer data block when captured.

        Return: dict{key: list} where key is the channel name and list is the captured data trace on this channel.
        """
        # Check for data collection to finish using ps4000aIsReady
        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        while ready.value == check.value:
            status_temp = ps.ps4000aIsReady(self.c_handle, ctypes.byref(ready))
        # create overflow loaction
        overflow = ctypes.c_int16()
        # create converted type maxSamples
        cmaxSamples = ctypes.c_int32(self.block_size)
        status = ps.ps4000aGetValues(self.c_handle,
                                    0, 
                                    ctypes.byref(cmaxSamples), 
                                    0, 
                                    0, 
                                    0, 
                                    ctypes.byref(overflow))
        assert_pico_ok(status)

        def convert_ADC_units():
            # Convert ADC counts data to mV
            self.buffers = {chl: adc2mV(buffer, self.channel_ranges[chl], self.max_ADC) for
                            chl, buffer in self.buffers.items()}
            self.voltage_unit = 'mV'
        convert_ADC_units()

        # #TODO temporary figure stuff do this properly later
        # if show_traces: 
        #     fig, ax = plt.subplots()
        #     sample_id = np.linspace(1, self.block_size, self.block_size) #change this to timestamps later
        #     sample_values = [chl for chl in self.buffers.values()]
        #     for chl in sample_values:
        #         ax.plot(sample_id, chl)
        #     fig.show()

        return self.buffers

