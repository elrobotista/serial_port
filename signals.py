import numpy as np
import threading
import copy
import logging
import math
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib
import time
import serial
import json
import sys
from abc import ABCMeta, abstractmethod
from Queue import Queue
import argparse
import time

logging.basicConfig(level = logging.DEBUG)
logging.getLogger().setLevel(logging.INFO)

def create_axes(title = None, xlabel = None, ylabel = None, legend = None):
    '''Create a figure with modified parameters so that it looks more
    aesthetic. @title is the figure's title, @xlabel is the x-axis' label,
    @ylabel, the y-axis' label and @legend holds the lines labels.'''
    fig = plt.figure()
    ax = plt.gca()
    if title:
        ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if legend:
        ax.legend(legend, loc = 'best', frameon = False)
    ax.spines['bottom'].set_linewidth(2)
    ax.spines['left'].set_linewidth(2)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.xaxis.set_ticks_position('bottom')
    ax.yaxis.set_ticks_position('left')
    ax.tick_params(labelsize = 14)
    ax.yaxis.grid(True, which = 'major')
    ax.xaxis.grid(True, which = 'major')
    return fig, ax

def remove_from_list(data, keep_data):
    '''Remove elements from list @data so that the length matches @keep_data'''    
    n = len(data) - keep_data
    if n <= 0:
        return data
    else:
        logging.debug('Removing %s from list', n)
        return data[:n]


def remove_from_ndarray(data, keep_data):
    '''Remove elements from @data ndarray so that the length matches @keep_data
    '''
    n = data.size - keep_data
    if n <= 0:
        return data
    else:
        logging.debug('Removing %s from ndarray', n)
        return np.delete(data, slice(0, n))
        
class Buffer(object):

    def __init__(self, names, on_new_data = None, keep_data = 300):
        self.on_new_data = on_new_data
        self.keep_data = keep_data
        self.names = names
        self.buffer = {name: Queue() for name in names}
        
    def _new_data_callback(self, *params):
        pass

    def has_data(self, name):
        '''Determine if buffer with @name has data stored. Returns the length of
        the list that hols data if there is. Returns 0 if there is no data. 
        Returns -1 if there is no buffer that matches @name.'''
        if self.buffer.has_key(name):
            return self.buffer[name].qsize()
        else:
            return -1

    def add_dict_data(self, data_dict):
        '''Add data to every buffer using @data_dict dictionary.''' 
        for name, data in data_dict.iteritems():
            self.add_data(name, data)

    def add_data(self, name, data):
        '''Add @data to the buffer with key that matches @name.'''
        if not self.buffer.has_key(name):
            return
        if not self.buffer[name].full():
            self.buffer[name].put(data)
        else:
            logging.warn('Queue %s is full!', name)        

    def get_data(self, name, n = 0):
        '''Returns @n amount of data in signal @name. If n == 0, all data in 
        the buffer is returned. if n < 0, a ValueError exception is raised.'''
        if n == 0:
            # Get copy of list. If data = self.buffer[name] gets a reference.
            # When the values are cleared, the returned values get cleared
            # as well.
            data = []
            while not self.buffer[name].empty():
                data.append(self.buffer[name].get())            
        elif n > 0:
            while n > 0 and not self.buffer[name].empty():
                data.append(self.buffer[name].get())
                n -= 1
        elif n < 0:
            data = None
            raise ValueError('Cannot get negative amounts of data')
        return data 
  
  
class Signal(Buffer):
    '''Defines the interface for Signal. This class specifies how data is
    stored, deleted and passed on to a RealTimePlot object for visulization'''
    __metaclass__ = ABCMeta

    def __init__(self, names, on_new_data = None, on_connect = None,
    on_disconnect = None, rate = 10., keep_data = 300):
        '''@names are the labels on the signals that will be read, either from
        serial port, sockets or other interface. @on_new_data is a callback that
        fires every time new data arrives. @on_connect fires when connection
        is established. @on_discconect fires when the channel closes. @rate
        specfies the interval at which the channel will be polled for data.
        @keep_data specifies that amount of data that will be buffered.'''
        Buffer.__init__(self, names, on_new_data, keep_data)
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect   
        self.rate = rate
        self.is_streaming = False
        self.lock = threading.Lock()

    def _stream(self):    
        '''Called periodically to poll for new data from communication channel.'''
        self.lock.acquire()
        if self.is_connected():
            raw_data = self._readline()
            self.lock.release()
        else:
            logging.warn('Trying to read from a disconnected port!')
            self.lock.release()
            return
        try:
            json_data = json.loads(raw_data)
            logging.debug('json: %s', json_data)
            self.add_dict_data(json_data)
        except ValueError:
            pass
            #logging.error('Could not read data: %s', raw_data)
        if self.is_connected():
            threading.Timer(self.rate / 1000., self._stream).start()
        else:
            logging.warn('Not streaming anymore!')

    def start(self):            
        '''Connect and start receiving data.'''
        self.connect()
        if self.is_connected():
            self._stream()
            if self.on_connect:
                self.on_connect()
        else:
            raise ValueError('Conection must be established first!')
            
    def stop(self):
        '''Stop and close connection.'''
        self.disconnect()
        if not self.is_connected():
            if self.on_disconnect:
                self.on_disconnect()
        else:
            raise ValueError('Connection could not be terminated!')
            
    @abstractmethod
    def _readline(self, *params):
        '''Implement how a data line (string terminated with \n) is read.
        @params are parameters needed by the channel.'''
        pass
    
    @abstractmethod 
    def connect(self, *params):
        '''Implements how to connect to the channel. @params are parameters needed
        for connection.'''
        pass
        
    @abstractmethod
    def disconnect(self, *params):
        '''Implements how to disconnect from channel. @params are parameters needed
        to disconnect.'''
        pass
        
    @abstractmethod
    def is_connected(self, *params):
        pass
    

class SerialSignal(Signal):

    def __init__(self, names, port = '/dev/ttyACM0', baudrate = 9600,
    timeout = 0, rate = 10., on_new_data = None, on_connect = None,
    on_disconnect = None):
        '''@names specifies the labels of the signals expected from the serial
        port. @port is the name of the port, @baudrate is the connection's
        baudrate. @on_new_datam @on_connect and @on_disconnect are callbacks.
        @timeout specifies the timeout when data reading is attempeted. @rate
        specifies the interval at which data is polled.'''
        Signal.__init__(self, names, on_new_data, on_connect, on_disconnect)
        self.port = serial.Serial(port, baudrate, timeout = timeout)
        #self.connect(port, baudrate, timeout)

    def connect(self, *params):
        '''Attempt connection with @params.'''
        if self.is_connected():
            return
        if not self.port.is_open:
            self.port.flushInput()
            self.port.open()
        
    def _readline(self):
        '''Read a line of data.'''
        return self.port.readline()
    
    def is_connected(self, *params):
        return self.port.is_open
    
    def disconnect(self, *params):
        '''Attempt disconnection using @params.'''
        if not self.is_connected():
            return
        self.lock.acquire()
        self.port.close()
        self.lock.release()
        
        
class RealTimePlot(object):
    '''Defines how data received through a channel (serial port or sockets)
    is animated.'''

    def __init__(self, signal, legend = None, title = None, xlabel = None, ylabel = None,
    interval = 60, xlim = 300., ylim = [-2., 2.], keep_data = 300, 
    autoscroll = True, autoscale = True, ts = None):
        '''@signal is the object that holds data. @legend for the figure. @title for figure.
        @xlabel for figure. @ylabel for figure. @interval at which animation is updated.
        @blit for faster animation. @xlim x-axis limits. @ylim y-axis limits. @keep_data
        defines how much data is displayed on the figure.'''
        self.fig, self.ax = create_axes()
        if title is not None:
            self.ax.set_title(title)
        if xlabel is not None:
            self.ax.set_xlabel(xlabel)
        if ylabel is not None:
            self.ax.set_ylabel(ylabel)
        if legend == None:
            legend = signal.names
        self.lines = [plt.plot([], [], label = label, animated = True)[0] for label in legend]
        self._ylim = self.ax.get_ylim()
        self._xdata = np.arange(keep_data)
        if ts is not None:
            self._xdata = ts * self._xdata
        self.ax.set_xlim([self._xdata[0], self._xdata[-1]])
        #self.ax.set_ylim(ylim)
        self.autoscroll = autoscroll
        self.signal = signal
        self.keep_data = keep_data
        self.autoscale = autoscale
        if not self.autoscale:
            self.ax.set_ylim(ylim)
        # Do not turn off blit or this will break! For blit to be off and for this to work, the Line2D
        # objects must be added directly to the axes object. This might be a bug in matplotlib?
        self.now = time.time()
        self.animation = animation.FuncAnimation(self.fig, self.update, interval = interval, blit = True, frames = 500)
        self.keep_data = keep_data
        plt.legend()
        
    def _init_plot(self):
        pass
            
    def _handle_autoscroll(self, t):
        pass
               
    def _handle_autosize(self, t):
        pass
        
    def show(self):
        plt.show(block = False)

    def update(self, i):
        '''Gets called to redraw the plot. Should not be used by application
        code.'''
        logging.info('Time: %s', time.time() - self.now)
        self.now = time.time()
        if self.autoscale:
            self.ax.relim()
            self.ax.autoscale_view()
            if self.ax.get_ylim() != self._ylim:
                # Plot has autoscaled. Save current ylim to detect updates
                # and request plot to be updated so ticks are shown properly.
                self._ylim = self.ax.get_ylim()
                self.fig.canvas.draw()
        for name, line in zip(self.signal.names, self.lines):
            if self.signal.has_data(name) > 0:
                _, ly = line.get_data()
                ly = np.append(ly, self.signal.get_data(name))
                ly = remove_from_ndarray(ly, self.keep_data)
                line.set_data(self._xdata[:ly.size], ly)
            else:
                logging.warn('Signal has no data')
        return self.lines
    
if __name__ == '__main__':

    parser = argparse.ArgumentParser(description = 'Serial Port Monitor', )
    parser.add_argument('-p', '--port', action = 'store', dest = 'port', default = '/dev/ttyACM0')
    parser.add_argument('-b', '--baudrate', action = 'store', dest = 'baudrate', default = 115200, type = int)
    parser.add_argument('-n', '--names', action='append', dest='names', default=[], help='Signal labels')
    args = parser.parse_args()

    stream = SerialSignal(args.names, port = args.port, baudrate = args.baudrate)
    stream.start()
    r = RealTimePlot(stream, xlim = 300., keep_data = 300, ts = 0.01, ylim = (-2, 2))
    #r.animation.save('basic_animation.mp4', fps=30, extra_args=['-vcodec', 'libx264'])
    r.show()
    print '####################################################################'
    print '######################### El Robotista #############################'
    print '####################################################################'
    print '### Plot signals recieved through Serial Port in real time. V1.0 ###'
    print '####################################################################'
    while True:
        print 'Hit Q to exit.'
        if raw_input('> ').lower() == 'q':
            break
    print 'Bye.'
    stream.stop()
