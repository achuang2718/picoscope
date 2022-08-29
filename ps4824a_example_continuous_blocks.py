import numpy as np
from ps4824a_wrapper_blockmode_utils import Picoscope
import matplotlib.pyplot as plt
import time

my_picoscope = Picoscope(0, verbose=True)



my_picoscope.setup_channel('A',channel_range_mv=2000)
my_picoscope.setup_channel('B',channel_range_mv=2000)
my_picoscope.setup_block(block_size=10000, block_duration=0.01, pre_trigger_percent=0)
my_picoscope.setup_trigger('B',trigger_threshold_mv=1500)




with my_picoscope:
    with open('pico.csv', 'a') as f:
        try:
            while True:
                my_picoscope.run_block()
                buffers = my_picoscope.get_block_traces()
                traces_value = [val for val in buffers.values()]
                traces_mean, traces_std = np.mean(traces_value, axis = 1), np.std(traces_value, axis = 1)
                print('Trace mean: ', traces_mean, '\nTrace std:', traces_std)
                print('Waiting for next trace...')
                np.savetxt(f, [np.concatenate((traces_mean,traces_std))], delimiter = ',')
        except KeyboardInterrupt:
            print('Picoscope logging terminated by keyboard interrupt')