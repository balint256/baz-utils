#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  seq_tx.py
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

import sys, struct, socket, traceback, time

from optparse import OptionParser

def main():
	parser = OptionParser(usage="%prog: [options] <destination address>")
	
	parser.add_option("-d", "--delay", type="int", default=0, help="delay (ms) [default=%default]")
	parser.add_option("-r", "--repeat", action="store_true", default=True, help="repeat transmission")
	parser.add_option("-p", "--port", type="int", default=12345, help="port [default=%default]")
	parser.add_option("-P", "--pipe", action="store_true", default=False, help="use a pipe instead of a socket [default=%default]")
	parser.add_option("-L", "--limit", type="int", default=(2**16-1), help="limit [default=%default]")
	parser.add_option("-B", "--transport-buffer-size", type="int", default=1, help="request transport buffer size [default=%default]")
	
	(options, args) = parser.parse_args()
	
	options.delay /= 1000.0
	
	if len(args) < 1:
		if options.pipe:
			print "Supply pipe name"
		else:
			print "Supply destination address"
		return
	
	destination_addr = args[0]
	if not options.pipe:
		idx = destination_addr.find(':')
		if idx > -1:
			destination_addr = destination_addr[:idx]
			options.port = int(destination_addr[idx+1:])
	
	f, s = None, None
	if options.pipe:
		print "Opening:", destination_addr
		f = open(destination_addr, 'w')
		print "Opened:", destination_addr
	else:
		destination = (destination_addr, options.port)
		print "Connecting to:", destination
		
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		
		s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
		
		if options.transport_buffer_size > 0:
			print "SO_SNDBUF was", s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
			s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, options.transport_buffer_size)
			print "SO_SNDBUF  is", s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
		
		s.connect(destination)
		
		print "Connected"
	
	try:
		cnt = 0
		print "Sending"
		while cnt == 0 or options.repeat:
			#sys.stdout.write("Sending...")
			#sys.stdout.flush()
			for y in range(options.limit):
				buf = struct.pack("I", y)
				if s:
					s.send(buf)
				if f:
					f.write(buf)
				if options.delay > 0.0:
					time.sleep(options.delay)
			sys.stdout.write(".")
			sys.stdout.flush()
			#print "done!"
			cnt += 1
	except KeyboardInterrupt:
		print
		print "Stopped"
	except Exception, e:
		print "Unhandled exception:", e
		print traceback.format_exc()
	
	if s:
		s.close()
	if f:
		f.close()
	
	return 0

if __name__ == '__main__':
	main()
