#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  realtime_graph_server.py
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

import traceback, threading, sys
from optparse import OptionParser
try:
	from xmlrpc.server import SimpleXMLRPCServer
except:
	from SimpleXMLRPCServer import SimpleXMLRPCServer

import realtime_graph# as _realtime_graph

try:
	import matplotlib
except:
	matplotlib = None

#class realtime_graph(_realtime_graph):
#	def _create_figure(self, *args, **kwds):
#		_realtime_graph._create_figure(*args, **kwds)
#		if self.parent is None:
#			pass

class GraphServer():
	def __init__(self, use_queue):
		self._use_queue = use_queue
		self._graphs = {}
		self._last_id = 0
		self._created_event = threading.Event()
		self._dispatch_event = threading.Event()
		self._processed_event = threading.Event()
		self._lock = threading.Lock()
		self._queue = []
		#self._last_created_graph = None
		self._created_graphs = []
	def get_created_graph(self):
		#if self._last_created_graph is None:
		if len(self._created_graphs) == 0:
			return None
		#return self._last_created_graph
		with self._lock:
			for g in self._created_graphs:
				if g.is_created():
					return g
		return None
	def get_last_graph(self):
		if self._last_id == 0:
			return None
		return self._graphs[self._last_id]
	def get_commands(self):
		with self._lock:
			q = self._queue
			self._queue = []
			return q
	def has_commands(self):
		with self._lock:
			return len(self._queue)
	def _dispatch(self, method, params):
		if method == "_create":
			parent_id = params[4]	# MAGIC
			print("Parent ID:", parent_id)
			if parent_id is not None:
				if self._graphs.has_key(parent_id):
					params = list(params)
					params[4] = self._graphs[parent_id]
				else:
					print("Parent graph #%d does not exist" % (parent_id))
			g = realtime_graph.realtime_graph(*params)
			self._last_id += 1
			self._graphs[self._last_id] = g
			print("Created graph #%d:" % (self._last_id), params)
			if g.is_created():
				print("Created on creation")
				#self._last_created_graph = g
				with self._lock:
					self._created_graphs += [g]
					print("%d created graphs" % (len(self._created_graphs)))
					self._created_event.set()
			return self._last_id
		
		#if method == 'run_event_loop' and self._use_queue:
		#	# FIXME: Sleep?
		#	return None
		
		#if method in ['go_modal']:
		#	while True:
		#		with self._lock:
		#			if len(self._queue) == 0:
		#				break
		#		print("Waiting for cleared queue")
		#		self._processed_event.wait()
		#	print("Dispatching", method)
		#	res = self.dispatch(method, params)
		#	print("Done:", res)
		#	return res
		
		if self._use_queue:
			with self._lock:
				self._queue += [(method, params)]
				self._processed_event.clear()
				self._dispatch_event.set()
			return None
		
		return self.dispatch(method, params)
	def dispatch(self, method, params):
		if len(params) == 0:
			print("Not ID supplied for method:", method)
			return None
		graph_id = params[0]
		if not isinstance(graph_id, int):
			print("First argument not int:", graph_id)
			return None
		params = params[1:]
		if not self._graphs.has_key(graph_id):
			print("Invalid graph ID:", graph_id)
			return None
		g = self._graphs[graph_id]
		if not hasattr(g, method):
			print("Invalid method:", method)
			return None
		fn = getattr(g, method)
		try:
			#print(graph_id, method)
			#print(graph_id, method, params)
			was_created = g.is_created()
			res = fn(*params)
			if was_created and not g.is_created():
				#if self._last_created_graph == g:
				#	self._last_created_graph = None
				with self._lock:
					if g in self._created_graphs:
						print("Removing graph #%d from created list:" % (graph_id))
						self._created_graphs.remove(g)
					else:
						print("Graph %d not in created graph list" % (graph_id))
			elif not was_created and g.is_created():
				#print("Created on", method)
				#self._last_created_graph = g
				with self._lock:
					self._created_graphs += [g]
					self._created_event.set()
			return res
		except Exception as e:
			print("Exception while running method '%s' with args:" % (method), params)
			traceback.print_exc()
			return None

class MySimpleXMLRPCServer(SimpleXMLRPCServer):
	pass
	#def _dispatch(self, method, params):

def main():
	parser = OptionParser(usage="%prog: [options]")
	
	parser.add_option("-a", "--address", type="string", default="0.0.0.0", help="server address [default=%default]")
	parser.add_option("-p", "--port", type="int", default=8000, help="server port [default=%default]")
	parser.add_option("-s", "--single-thread", action="store_true", default=False, help="run in a single thread [default=%default]")
	parser.add_option("-t", "--timeout", type="float", default=0.1, help="GUI event timeout [default=%default]")
	
	(options, args) = parser.parse_args()
	
	server = MySimpleXMLRPCServer((options.address, options.port), logRequests=False, allow_none=True) #requestHandler=RequestHandler
	
	instance = GraphServer(use_queue=not options.single_thread)
	server.register_instance(instance)
	
	font = {
		#'family' : 'normal',
		#'weight' : 'bold',
		'size'   : 10
	}
	
	if matplotlib is not None:
		matplotlib.rc('font', **font)
	
	if options.single_thread:
		try:
			server.serve_forever()
		except KeyboardInterrupt:
			pass
	else:
		server_thread = threading.Thread(target=server.serve_forever)
		server_thread.setDaemon(True)
		server_thread.start()
		
		#print("Waiting for first graph...")
		#instance._created_event.wait()
		#print("First graph created")
		#first_graph = instance.get_last_graph()
		
		#dummy_graph = realtime_graph.realtime_graph(title="Dummy", show=True)
		#instance._created_graphs += [dummy_graph]
		
		#first_graph = None
		have_graph = False
		while True:
			if instance.get_created_graph() is None:
				if not instance.has_commands():
					if have_graph:
						print("Waiting...")
						have_graph = False

						instance._dispatch_event.wait()
						instance._dispatch_event.clear()
					else:
						print("[Waiting...]")
						try:
							while not instance._created_event.wait(options.timeout):
								pass
						except KeyboardInterrupt:
							break
						instance._created_event.clear()
					print("[Cleared]")
			else:
				have_graph = True
				#print("Running event loop...")
				#sys.stdout.write('.')
				#sys.stdout.flush()
				#instance.get_created_graph()._redraw(quick=True)
				instance.get_created_graph().run_event_loop(options.timeout)
			
			cmds = instance.get_commands()
			if len(cmds) > 0:
				#print("Got %d commands" % (len(cmds)))
				sys.stdout.write('.')
				sys.stdout.flush()

				for cmd in cmds:
					instance.dispatch(cmd[0], cmd[1])

				#instance.get_created_graph()._redraw(quick=True)
				#instance.get_created_graph().run_event_loop(options.timeout)
			
			instance._processed_event.set()
	
	return 0

if __name__ == '__main__':
	main()
