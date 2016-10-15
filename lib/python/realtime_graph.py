#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  realtime_graph.py
#  
#  Copyright 2014 Balint Seeber <balint256@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  

# FIXME:
#   Detect window close (e.g. wx._core.PyDeadObjectError)
#   Replace horizontal line code with MPL's in-built one

import os, xmlrpclib, base64

import numpy

try:
    import matplotlib
    import matplotlib.pyplot as pyplot
except Exception, e:
    print "Failed to import matplotlib:", e
    matplotlib = None
    pyplot = None

def ndarray_serialiser(self, value, write):
    write("<value><ndarray>")
    write(base64.b64encode(value.dumps()))
    write("</ndarray></value>\n")
xmlrpclib.Marshaller.dispatch[numpy.ndarray] = ndarray_serialiser

def ndarray_parser(unmarshaller, data):
    unmarshaller.append(numpy.loads(base64.b64decode(data)))
    unmarshaller._value = 0
xmlrpclib.Unmarshaller.dispatch['ndarray'] = ndarray_parser

def float64_serialiser(self, value, write):
    write("<value><float64>")
    write(base64.b64encode(value.dumps()))
    write("</float64></value>\n")
xmlrpclib.Marshaller.dispatch[numpy.float64] = float64_serialiser

def float64_parser(unmarshaller, data):
    unmarshaller.append(numpy.loads(base64.b64decode(data)))
    unmarshaller._value = 0
xmlrpclib.Unmarshaller.dispatch['float64'] = float64_parser

class _realtime_graph():
    def __init__(self, title="Real-time Graph", sub_title="", x_range=None, show=False, parent=None, manual=False, pos=111, redraw=True, figsize=None, padding=None, y_limits=None, gui_timeout=0.1, data=None, x=None, verbose=False):
        self.verbose = verbose
        self.parent = parent
        
        if isinstance(x_range, float) or isinstance(x_range, int):
            x_range = (0, x_range-1)
            self._log("Creating x_range: {}", x_range)
        
        self.title_text = title
        self.sub_title_text = sub_title
        self.x_range = x_range
        self.y_limits = y_limits
        
        self.figsize = figsize
        self.pos = pos
        self.padding = padding
        
        self.figure = None
        self.title = None
        #self.plot = None
        self.plots = []
        self.subplot = None # Axes
        self.points = []
        
        self._gui_timeout = gui_timeout
        
        self._horz_lines = []
        self._horz_lines_map = {}
        
        self._vert_lines = []
        self._vert_lines_map = {}
        
        if show:
            self._log("Showing from constructor")
            self._create_figure(data=data, x=x, manual=manual, redraw=redraw)

    def _log(self, msg, *args, **kwds):
        if self.verbose:
            if isinstance(msg, str):
                formatted_msg = msg.format(*args, **kwds)
            else:
                formatted_msg = str(msg)
            print "realtime_graph: {}".format(formatted_msg)
    
    def _calc_agg_x_range(self, xx):
        if len(xx) == 0:
            self._log("No X data so no X range")
            return None
        
        agg_x_range = [None, None]
        for _x in xx:
            _x_range = (min(_x), max(_x))
            if agg_x_range[0] is None or _x_range[0] < agg_x_range[0]:
                agg_x_range[0] = _x_range[0]
            if agg_x_range[1] is None or _x_range[1] < agg_x_range[1]:
                agg_x_range[1] = _x_range[1]

        self._log("Calculated X range: {}", agg_x_range)
        
        return agg_x_range
    
    def _fuse_coords(self, data, x):
        xx = []
        dd = []

        # array([1,2,3,...])
        # (y, x) -> [(y, x)]
        # [(y, x)]
        # [[1,2,3,...],...] -> [[1,2,3,...]], [[0..x0]] / ...
        # [[1,2,3,...],...], array([0..x]) -> [[1,2,3,...]], array([0..x]) / ..., array([0..x])
        # [[1,2,3,...],...], [[4,5,6,...],...],
        # [[1,2,3,...],...], [[4,5,6,...],None,...],
        # [[1,2,3,...],[1,2,3,...]], [[4,5,6,...]],
        
        if data is not None:
            if not isinstance(data, list):
                self._log("Data is not list, making list")
                data = [data]
            
            self._log("Fusing coords for {} series", len(data))

            idx = 1
            for d in data:
                if isinstance(d, tuple):
                    self._log("Series {} is tuple", idx)
                    dd += [d[0]]
                    xx += [d[1]]
                else:
                    self._log("Series {} is: {} ({}-{}, {} items)", idx, type(d), min(d), max(d), len(d))
                    dd += [d]
                    manual_x = False
                    if x is not None:
                        if isinstance(x, list):
                            if len(dd) <= len(x):
                                _x = x[len(dd)-1]
                                if _x is not None:
                                    self._log("Using supplied multi X series for series {}: {}-{} ({} items)", idx, min(_x), max(_x), len(_x))
                                    xx += [_x]
                                else:
                                    manual_x = True
                            else:
                                manual_x = True
                        else:
                            self._log("Using supplied single X series for series {}", idx)
                            xx += [x]
                    else:
                        manual_x = True
                    
                    if manual_x:
                        self._log("Manual X for series {} length {}", idx, len(d))
                        xx += [numpy.linspace(0, len(d) - 1, len(d))]

                idx += 1

        return xx, dd
    
    def clear(self, redraw=True):
        self._log("Clearing graph")
        for plot in self.plots:
            self.subplot.lines.remove(plot)
        self.plots = []
        if redraw:
            self._redraw()
    
    def is_created(self):
        return (self.figure is not None)
    
    def _destroy(self):
        self.figure = None
    
    def _handle_close(self, event):
        self._log("Closing")
        self._destroy()
    
    def _create_figure(self, data=None, x=None, meta={}, redraw=True, manual=False):
        if self.parent is None:
            self._log("Enabling interactive mode")
            pyplot.ion()    # Must be here
            
            kwds = {}
            if self.figsize is not None:
                kwds['figsize'] = self.figsize
            self._log("Creating figure with: {}", kwds)
            self.figure = pyplot.figure(**kwds)   # num=X
            
            self.figure.canvas.mpl_connect('close_event', self._handle_close)
            
            if self.padding is not None:
                self._log("Applying padding: {}", self.padding)
                self.figure.subplots_adjust(**self.padding)
            
            self.title = self.figure.suptitle(self.title_text)
            if manual == False:
                self.subplot = self.figure.add_subplot(self.pos)
        else:
            self._log("Adding subplot to parent")
            self.subplot = self.parent.figure.add_subplot(self.pos)
        
        if self.subplot is not None:
            self.subplot.grid(True)
            self.subplot.set_title(self.sub_title_text)
            
            xx, dd = self._fuse_coords(data, x)
            
            if self.x_range is None and len(xx) > 0:
                self.x_range = self._calc_agg_x_range(xx)
            
            #if x is None:
                #x = numpy.array([0])
                #if self.x_range is None and data is not None:
                #    self._calc_x_range(data)
                #if self.x_range is not None:
                #    x = numpy.linspace(self.x_range[0], self.x_range[1], self.x_range[1]-self.x_range[0])
                
            #    if data is not None:
            #        self._calc_x_range(data)
            #        x = numpy.linspace(self.x_range[0], self.x_range[1], len(data[0]))
            #else:
            #    self.x_range = (min(x), max(x)) # FIXME: Only if x_range is not None?
            
            #if data is None:
            #    data = numpy.array([0]*len(x))
            
            #if data is not None and x is not None:
                #self.plot, = pyplot.plot(x, data)
                #self.plot, = self.subplot.plot(x, data)
                
                #self.plots += self.subplot.plot([(x, _y) for _y in data])  # FIXME
            #    for d in data:
            #        self.plots += self.subplot.plot(x, d)
            
            cnt = 0
            _meta = meta
            for d in dd:
                if isinstance(meta, list):
                    _meta = meta[cnt]
                self._log("Adding series {} of type {} with meta {}", (cnt+1), type(d), _meta)
                self.plots += self.subplot.plot(xx[cnt], d, **_meta)
                cnt += 1
            
            # This was moved left one indent level ('_apply_axis_limits' is safe)
            
            #self.plot.axes.grid(True)
            #self.plot.axes.set_title(self.sub_title_text)
        
            #self.plot.axes.set_xlim([min(x),max(x)])
            self._apply_axis_limits()
        
        if redraw:
            self._redraw()
    
    def _apply_axis_limits(self):
        if self.x_range is not None:
            self._log("Applying xlim: {}", self.x_range)
            #self.plot.axes.set_xlim(self.x_range)
            self.subplot.set_xlim(self.x_range)
        if self.y_limits is not None:
            self._log("Applying ylim: {}", self.y_limits)
            #self.plot.axes.set_ylim(self.y_limits)
            self.subplot.set_ylim(self.y_limits)
    
    def _calc_x_range(self, data, store=True):
        if isinstance(data, list):
            #data = data[0]
            max_len = 1
            for d in data:
                if isinstance(d, tuple):
                    d = d[0]
                max_len = max(max_len, len(d))
            x_range = (0, max_len - 1)
        else:
            if isinstance(data, tuple):
                data = data[0]
            
            x_range = (0, len(data) - 1)

        self._log("Calculated X range: {}", x_range)
        
        if store:
            self._log("Storing calculated X range: {}", x_range)
            self.x_range = x_range
        
        return x_range
    
    def set_y_limits(self, y_limits):
        self._log("Y limits set to: {}", y_limits)
        self.y_limits = y_limits
    
    def set_data(self, data, x=None, meta={}, auto_x_range=True, x_range=None, autoscale=True, redraw=False):  # Added auto_x_range/x_range/autoscale before redraw
        if data is None:
            self._log("No data to set")
            return
        if self.subplot is None:
            if redraw:
                self._log("While setting data: creating non-existent subplot")
                #self._create_figure(data=data, x=x, meta=meta, redraw=redraw)
                self._create_figure()
            else:
                self._log("While setting data: no subplot but not redrawing")
                return
        #elif not isinstance(data, list):   # Done in fuse coords
        #    data = [data]
        
        #self.figure.canvas.flush_events()
        
        if x_range is not None:
            self._log("Using custom X range: {}", x_range)
            self.x_range = x_range
        
        xx, dd = self._fuse_coords(data, x)
        
        #if self.x_range is None:
        #    self._calc_x_range(data)
        if (self.x_range is None or auto_x_range) and len(xx) > 0:
            self._log("Forcing calculation of X range (auto X range: {})", auto_x_range)
            self.x_range = self._calc_agg_x_range(xx)
            #print "Calculated agg X range:", self.x_range
            self._log("Applying newly calculated xlim: {}", self.x_range)
            self.subplot.set_xlim(self.x_range)
        
        #if x is None:
        #    x = numpy.linspace(self.x_range[0], self.x_range[1], len(data[0]))
        #elif auto_x_range and x_range is None:
        #    self.x_range = (min(x), max(x))
        
        cnt = 0
        _meta = meta
        #for d in data:
        for d in dd:
            if isinstance(meta, list):
                _meta = meta[cnt]
            if cnt >= len(self.plots):
                #self.plots += self.subplot.plot(x, d)
                self.plots += self.subplot.plot(xx[cnt], d, **_meta)
            else:
                #self.plots[cnt].set_data(x, d)
                self.plots[cnt].set_data(xx[cnt], d, **_meta)
            cnt += 1
        
        if autoscale:
            # All three are necessary!
            self.subplot.relim()
            self.subplot.autoscale_view()
            #self.plot.axes.set_xlim(self.x_range)
            self._apply_axis_limits()
        
        if self.x_range is not None:
            for line in self._horz_lines:
                line_x, line_y = line.get_data()
                value = line_y[0]
                line.set_data(numpy.array([self.x_range[0], self.x_range[1]]), numpy.array([value, value]))
        
        if self.y_limits is not None:
            for line in self._vert_lines:
                line_x, line_y = line.get_data()
                value = line_x[0]
                line.set_data(numpy.array([value, value]), numpy.array([self.y_limits[0], self.y_limits[1]]))
        
        if redraw:
            self._redraw()
    
    def update(self, data=None, title=None, sub_title=None, x=None, meta={}, auto_x_range=True, x_range=None, autoscale=True, points=None, clear_existing_points=True, redraw=True):
        self._log("Updating")
        if title is not None:
            self.set_title(title)
        if sub_title is not None:
            self.set_sub_title(sub_title)
        if self.parent is None and self.figure is None:
            self._create_figure(data=data, x=x, redraw=False)   # FIXME: 'auto_x_range', 'x_range'
        elif data is not None:
            self.set_data(data=data, x=x, meta=meta, auto_x_range=auto_x_range, x_range=x_range, autoscale=autoscale)
        if points is not None:
            if clear_existing_points:
                self.clear_points()
            if len(points) > 0:
                self.add_points(points)
        if redraw:
            self._redraw()
    
    def clear_points(self, redraw=False):
        self._log("Clearing points")
        for line in self.points:
            self.subplot.lines.remove(line)
        self.points = []
        if redraw:
            self._redraw()
    
    def add_points(self, points, marker='mo', redraw=False):
        if len(points) == 0:
            self._log("No points to add")
            return
        self._log("Adding {} points", len(points))
        self.points += self.subplot.plot(numpy.array(map(lambda x: x[0], points)), numpy.array(map(lambda x: x[1], points)), marker)    # FIXME: Better way to do this?
        if redraw:
            self._redraw()
    
    def redraw(self):
        self._log("External redraw called")
        self._redraw()
    
    def _redraw(self, quick=False):
        if self.parent is None:
            try:
                if self.figure is None:
                    self._log("During redraw creating figure")
                    self._create_figure(redraw=False)
                self._log("Drawing and flushing events")
                self.figure.canvas.draw()
                self.figure.canvas.flush_events()
                if quick == False:
                    self._log("Running event loop once with timeout {}", self._gui_timeout)
                    self.figure.canvas.start_event_loop(timeout=self._gui_timeout)
                self.figure.canvas.flush_events()
            except RuntimeError, e:
                self._log("During redraw RuntimeError, re-creating figure: {}", e)
                self._create_figure()
        else:
            self.parent._redraw(quick=quick)
    
    def run_event_loop(self, timeout=None):
        if timeout is None:
            timeout = self._gui_timeout
        #self._log("Running event loop with timeout {}", timeout)   # Would produce too much output
        self.figure.canvas.start_event_loop(timeout=timeout)
    
    def go_modal(self):
        if self.figure is None:
            self._log("Cannot go modal without figure")
            return False
        self._log("Going modal")
        return self.figure.canvas.start_event_loop()
    
    def set_title(self, title, redraw=False):
        self._log("Setting title to: {}", title)
        self.title_text = title
        if self.title is not None:
            self.title.set_text(title)
            if redraw:
                self._redraw()
    
    def set_sub_title(self, sub_title, redraw=False):
        self._log("Setting subtitle to: {}", sub_title)
        self.sub_title_text = sub_title
        if self.subplot is not None:
            self.subplot.set_title(sub_title)
            #self.plot.axes.set_title(self.sub_title_text)  # Same
            if redraw:
                self._redraw()
    
    def add_horz_line(self, value, color='red', linestyle='-', id=None, replace=True, redraw=False):
        if id in self._horz_lines_map.keys():
            if not replace:
                return
            self.remove_horz_line(id)
        line = matplotlib.lines.Line2D(numpy.array([self.x_range[0], self.x_range[1]]), numpy.array([value, value]), linestyle=linestyle, color=color)
        self._horz_lines += [line]
        if id is not None:
            self._horz_lines_map[id] = line
        self.subplot.add_line(line)
        if redraw:
            self._redraw()
    
    def remove_horz_line(self, id):
        if not id in self._horz_lines_map.keys():
            self._log("horizontal line {} does not exist", id)
            return
        self._log("Removing horizontal line {}", id)
        line = self._horz_lines_map[id]
        self._horz_lines.remove(line)
        self.subplot.lines.remove(line)
        del self._horz_lines_map[id]
    
    def add_vert_line(self, value, color='black', linestyle='-', id=None, replace=True, redraw=False):
        if id in self._vert_lines_map.keys():
            if not replace:
                return
            self.remove_vert_line(id)
        if self.y_limits is None:
            return
        line = matplotlib.lines.Line2D(numpy.array([value, value]), numpy.array([self.y_limits[0], self.y_limits[1]]), linestyle=linestyle, color=color)
        self._vert_lines += [line]
        if id is not None:
            self._vert_lines_map[id] = line
        self.subplot.add_line(line)
        if redraw:
            self._redraw()
    
    def remove_vert_line(self, id):
        if not id in self._vert_lines_map.keys():
            self._log("Vertical line {} does not exist", id)
            return
        self._log("Removing vertical line {}", id)
        line = self._vert_lines_map[id]
        self._vert_lines.remove(line)
        self.subplot.lines.remove(line)
        del self._vert_lines_map[id]
    
    def save(self, output_name):
        if self.parent is not None:
            return self.parent.save(output_name)
        self._log("Saving to {}", output_name)
        self.figure.savefig(output_name)
        return True
    
    def close(self):
        self._log("Closing")
        pyplot.close(self.figure)
        self._destroy()

_default_remote_address = ""

class remote_realtime_graph():  #_realtime_graph
    def __init__(self, title="Real-time Graph", sub_title="", x_range=None, show=False, parent=None, manual=False, pos=111, redraw=True, figsize=None, padding=None, y_limits=None, gui_timeout=0.1, data=None, x=None, address=""):
        if len(address) == 0:
            address = _default_remote_address
        if len(address) == 0:
            raise Exception("Cannot create remote_realtime_graph without an address")
        self._proxy = xmlrpclib.ServerProxy(address, allow_none=True)
        parent_id = None
        if parent is not None:
            parent_id = parent._id
        self._id = self._proxy._create(
            title,
            sub_title,
            x_range,
            show,
            parent_id,
            manual,
            pos,
            redraw,
            figsize,
            padding,
            y_limits,
            gui_timeout,
            data,
            x
        )
    def __nonzero__(self):
        return 1
    # clear
    # set_y_limits
    # clear_points
    # redraw
    # run_event_loop
    # go_modal
    # set_title
    # set_sub_title
    # remove_horz_line
    # remove_vert_line
    # save
    # close
    def _proxy_fn(self, name, *args, **kwds):
        #print "Proxying %s:" % (name), args, kwds
        fn = getattr(self._proxy, name)
        if len(kwds) > 0:
            for k in kwds.keys():
                print "Appending to '%s' arg list: %s" % (name, k)
                args += kwds[k]
        fn(self._id, *args)
    def __getattr__(self, name):
        return lambda *args, **kwds: self._proxy_fn(name, *args, **kwds)
    def set_data(self, data, x=None, meta={}, auto_x_range=True, x_range=None, autoscale=True, redraw=False):
        self._proxy.set_data(self._id,
            data,
            x,
            meta,
            auto_x_range,
            x_range,
            autoscale,
            redraw
        )
    def update(self, data=None, title=None, sub_title=None, x=None, meta={}, auto_x_range=True, x_range=None, autoscale=True, points=None, clear_existing_points=True, redraw=True):
        self._proxy.update(self._id,
            data,
            title,
            sub_title,
            x,
            meta,
            auto_x_range,
            x_range,
            autoscale,
            points,
            clear_existing_points,
            redraw
        )
    def add_points(self, points, marker='mo', redraw=False):
        self._proxy.add_points(self._id,
            points,
            marker,
            redraw
        )
    def add_horz_line(self, value, color='red', linestyle='-', id=None, replace=True, redraw=False):
        self._proxy.add_horz_line(self._id,
            value,
            color,
            linestyle,
            id,
            replace,
            redraw
        )
    def add_vert_line(self, value, color='black', linestyle='-', id=None, replace=True, redraw=False):
        self._proxy.add_vert_line(self._id,
            value,
            color,
            linestyle,
            id,
            replace,
            redraw
        )

RT_GRAPH_KEY = "RT_GRAPH_ADDR"
if matplotlib and pyplot:
    realtime_graph = _realtime_graph
else:
    print "Only remote_realtime_graph will be available"
    realtime_graph = remote_realtime_graph
if os.environ.has_key(RT_GRAPH_KEY) and len(os.environ[RT_GRAPH_KEY]) > 0:
    #global _default_remote_address, realtime_graph
    _default_remote_address = os.environ[RT_GRAPH_KEY]
    print "Default remote real-time graph address:", _default_remote_address
    realtime_graph = remote_realtime_graph

def main():
    graph = realtime_graph()
    graph.update(numpy.linspace(0, 10))
    graph.go_modal()
    return 0

if __name__ == '__main__':
    main()
