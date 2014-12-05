#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  seq_rx.py
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

import sys, struct, socket, traceback, os, fcntl, time

from optparse import OptionParser

running = False

def main():
	parser = OptionParser(usage="%prog: [options] <server address>")
	
	parser.add_option("-p", "--port", type="int", default=12345, help="port [default=%default]")
	parser.add_option("-b", "--buffer-size", type="int", default=1024, help="receive buffer size [default=%default]")
	parser.add_option("-P", "--pipe", action="store_true", default=False, help="use a pipe instead of a socket [default=%default]")
	parser.add_option("-L", "--limit", type="int", default=(2**16-1), help="limit [default=%default]")
	parser.add_option("-i", "--interval", type="int", default=1024, help="update interval [default=%default]")
	parser.add_option("-l", "--listen", action="store_true", default=False, help="listen on a socket instead of connecting to a server [default=%default]")
	parser.add_option("-B", "--transport-buffer-size", type="int", default=1, help="request transport buffer size [default=%default]")
	
	(options, args) = parser.parse_args()
	
	if (len(args) < 1) and (not options.listen):
		if options.pipe:
			print "Supply pipe name"
		else:
			print "Supply destination address"
		return
	
	destination_addr = None
	if len(args) > 0:
		destination_addr = args[0]
		if not options.pipe:
			idx = destination_addr.find(':')
			if idx > -1:
				destination_addr = destination_addr[:idx]
				options.port = int(destination_addr[idx+1:])
			destination = (destination_addr, options.port)
	
	int_len = struct.calcsize("I")
	
	buf = ""
	
	s, f, l = None, None, None
	hush_open_message = False
	last = None
	cnt = 0
	num_cnt = 0
	dot_cnt = 0
	
	try:
		if not options.pipe and options.listen:
			l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			if destination_addr is None:
				destination_addr = "0.0.0.0"
			listen_addr = (destination_addr, options.port)
			l.bind(listen_addr)
			l.listen(1)
			print "Listening on:", listen_addr
		
		while True:
			if s:
				s.close()
				s = None
			
			if options.pipe:
				if not hush_open_message:
					print "Opening:", destination_addr
				
				f = open(destination_addr, 'r')
				
				if not hush_open_message:
					print "Opened:", destination_addr
			else:
				if options.listen:
					s, addr = l.accept()
					print "Accepted connection from:", addr
					last = None
					dot_cnt = 0
				else:
					if not hush_open_message:
						print "Connecting to:", destination
					
					s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					s.connect(destination)
				
				if options.transport_buffer_size > 0:
					print "SO_RCVBUF was", s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
					s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, options.transport_buffer_size)
					print "SO_RCVBUF  is", s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
				
				if not hush_open_message:
					print "Connected"
			
			while True:
				if s:
					try:
						b = s.recv(options.buffer_size)
						if len(b) == 0:
							break
						buf += b
					except socket.error, e:
						#if e.errno == 115:	# In progress
						#	continue
						#elif e.errno == 11:	# Unavailable
						#	break
						#else:
						#	raise e
						print
						print e
						break
				if f:
					try:
						buf += f.read(options.buffer_size)
						hush_open_message = False
					except IOError, e:
						if e.errno == 11:
							hush_open_message = True
						else:
							print
							print e
						break
				
				while buf != "":
					if len(buf) < int_len:
						break
					
					cnt, = struct.unpack("I", buf[0:int_len])
					
					if last is None:
						if dot_cnt > 0:
							print
							dot_cnt = 0
						print "-> %08d" % (cnt)
					else:
						expecting = (last + 1) % options.limit
						if cnt != expecting:
							if dot_cnt > 0:
								print
								dot_cnt = 0
							diff = cnt - expecting
							print "!  %08d (expected: %08d, skipped: %08d)" % (cnt, expecting, diff)
					last = cnt
					
					buf = buf[int_len:]
					
					num_cnt += 1
					if num_cnt == options.interval:
						sys.stdout.write(".")
						sys.stdout.flush()
						dot_cnt += 1
						num_cnt = 0
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
	if l:
		l.close()
	
	return 0

if __name__ == '__main__':
	main()
