#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  img_rx.py
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

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np

running = False

def handle_close(evt):
	global running
	print
	print "Closed"
	running = False

def main():
	global running
	parser = OptionParser(usage="%prog: [options] <server address>")
	
	parser.add_option("-p", "--port", type="int", default=12345, help="port [default=%default]")
	parser.add_option("-b", "--buffer-size", type="int", default=1024, help="receive buffer size [default=%default]")
	parser.add_option("-t", "--gui-timeout", type="float", default=0.1, help="time to run event loop (s) [default=%default]")
	parser.add_option("-T", "--socket-timeout", type="float", default=0.001, help="time to block on socket (s) [default=%default]")
	parser.add_option("-P", "--pipe", action="store_true", default=False, help="use a pipe instead of a socket [default=%default]")
	parser.add_option("-l", "--listen", action="store_true", default=False, help="listen on a socket instead of connecting to a server [default=%default]")
	parser.add_option("-r", "--reset", action="store_true", default=False, help="reset image on new connection [default=%default]")
	parser.add_option("-L", "--gui-lines", type="int", default=1, help="run event loop on after updating this many scanlines [default=%default]")
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
				options.port = int(destination_addr[idx+1:])
				destination_addr = destination_addr[:idx]
			destination = (destination_addr, options.port)
	
	MAGIC = 0xFEDCBA98	# Assuming this is not a valid height
	MAGIC_packed = struct.pack("I", MAGIC)
	
	img_arr = None
	img_plot = None
	img_height = 0
	img_width = 0
	bpp = 0
	y = -1
	x = 0
	p = 0
	int_len = struct.calcsize("i")
	
	buf = ""
	
	plt.ion()
	
	def _fill_img(img_arr, bpp, y, x, p, data, update=True, fill=True):
		if img_arr is None:
			return y, x, p
		elif len(data) == 0:
			return y, x, p
		#bpp = 1
		#try:
		#	bpp = len((img_arr[0])[0])
		#except:
		#	pass
		if y >= len(img_arr) or y < 0:
			print "y = %d but image height = %d" % (y, len(img_arr))
			return y, x, p
		scanline = img_arr[y]
		for i in range(len(data)):
			if x >= len(scanline) or x < 0:
				print "x = %d but scanline length = %d" % (x, len(scanline))
				return y, x, p
			if bpp > 1:
				pixel = scanline[x]
				pixel[p] = ord(data[i])
				p += 1
				if p == bpp:
					p = 0
					x += 1
			else:
				scanline[x] = ord(data[i])
				x += 1
		if fill:
			_x = x
			for i in range(len(scanline) - (x+1)):
				if bpp > 1:
					pixel = scanline[_x]
					for j in range(bpp):
						pixel[j] = 0
				else:
					scanline[_x] = 0
				_x += 1
		if update:
			img_plot.set_data(img_arr)
			_refresh_plot(img_plot, 0, True)	# flush_events was False
		return y, x, p
	
	def _refresh_plot(img_plot, timeout=0, flush_events=True, draw=True):
		if not draw:
			return
		global running
		if img_plot is None:
			return
		if running == False:
			return
		img_plot.figure.canvas.draw()
		if flush_events:
			img_plot.figure.canvas.flush_events()
			if running == False:
				return
			if timeout > 0:
				img_plot.figure.canvas.start_event_loop(timeout=timeout)
			if running == False:	# Just in case (not thread safe)
				return
			if timeout > 0:	# No point in doing this again if not starting the event loop
				img_plot.figure.canvas.flush_events()
	
	running = True
	
	s, f, l = None, None, None
	hush_open_message = False
	
	try:
		if not options.pipe and options.listen:
			l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			if destination_addr is None:
				destination_addr = "0.0.0.0"
			listen_addr = (destination_addr, options.port)
			l.bind(listen_addr)
			l.listen(1)
			print "Listening on:", listen_addr
		
		while running:
			if s:
				s.close()
				s = None
			
			if options.pipe:
				if not hush_open_message:
					print "Opening:", destination_addr
				
				f = open(destination_addr, 'r')
				
				if img_plot:
					fl = fcntl.fcntl(f.fileno(), fcntl.F_GETFL)
					fcntl.fcntl(f.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)
				
				if not hush_open_message:
					print "Opened:", destination_addr
			else:
				if options.listen:
					print
					print "Listening for incoming connection..."
					s, addr = l.accept()
					print "Accepted connection from:", addr
				else:
					if not hush_open_message:
						print "Connecting to:", destination
					
					s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
					s.connect(destination)
				
				if options.transport_buffer_size > 0:
					print "SO_RCVBUF was", s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
					s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, options.transport_buffer_size)
					print "SO_RCVBUF  is", s.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
				
				if img_plot:
					s.settimeout(options.socket_timeout)
				
				if not hush_open_message:
					print "Connected"
				
				if options.reset:
					img_height, img_width, bpp = 0, 0, 0
			
			received_scanline_cnt = 0
			do_gui_update = True
			
			while running:
				if s:
					try:
						b = s.recv(options.buffer_size)
						if len(b) == 0:
							break
						buf += b
					except socket.timeout:
						if running == False:
							break
						_refresh_plot(img_plot, options.gui_timeout)
						continue
					except socket.error, e:
						#if e.errno == 115:	# In progress
						#	if img_plot:
						#		sys.stdout.write("*")
						#		sys.stdout.flush()
						#		_refresh_plot(img_plot)
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
						buf_read = f.read(options.buffer_size)
						hush_open_message = False
						if buf_read is None or len(buf_read) == 0:
							time.sleep(options.socket_timeout)
							continue
						buf += buf_read
					except IOError, e:
						if e.errno == 11:
							hush_open_message = True
						else:
							print
							print e
						break
				
				while buf != "" and running:
					idx = buf.find(MAGIC_packed)
					if idx == -1:
						y, x, p = _fill_img(img_arr, bpp, y, x, p, buf, do_gui_update)
						break
					
					if idx > 0:
						y, x, p = _fill_img(img_arr, bpp, y, x, p, buf[:idx], do_gui_update)
						if running == False:
							break
					
					buf = buf[idx:]
					
					if len(buf) < (int_len * 2):
						break
					
					dummy, _img_height = struct.unpack("Ii", buf[:(int_len * 2)])
					if _img_height == 0:
						y, x, p = _fill_img(img_arr, bpp, y, x, p, buf[:len(MAGIC_packed)], do_gui_update)
						buf = buf[(int_len * 2):]
						sys.stdout.write("*")
						sys.stdout.flush()
						continue
					
					if len(buf) < (int_len * 5):
						break
					
					dummy, _img_height, _img_width, _bpp, _y = struct.unpack("Iiiii", buf[:(int_len * 5)])
					
					if not _bpp in [1, 3, 4]:
						sys.stdout.write("!")
						sys.stdout.flush()
					elif _img_height != img_height or _img_width != img_width or _bpp != bpp:
						img_width, img_height = _img_width, _img_height
						bpp = _bpp
						print "Size: (%d, %d) @ %d BPP" % (img_width, img_height, bpp)
						black_pixel = np.asarray([0] * bpp, dtype=np.uint8)
						white_pixel = np.asarray([255] * bpp, dtype=np.uint8)
						def _gen_scanline(length, even=0):
							if even % 2:
								scanline = np.copy(white_pixel)
							else:
								scanline = np.copy(black_pixel)
							for l in range(length-1):
								if (l + even) % 2:
									scanline = np.vstack((scanline, black_pixel))
								else:
									scanline = np.vstack((scanline, white_pixel))
							return scanline
						odd_scanline, even_scanline = _gen_scanline(img_width, 0), _gen_scanline(img_width, 1)
						img_arr = np.copy(odd_scanline)
						for h in range(img_height-1):
							if (h % 2):
								scanline = odd_scanline
							else:
								scanline = even_scanline
							img_arr = np.hstack((img_arr, scanline))
						if bpp > 1:
							img_arr = img_arr.reshape((img_height, img_width, bpp))
						print img_arr.shape, img_arr.dtype
						if img_plot is None:
							if s:
								s.settimeout(options.socket_timeout)
							if f:
								fl = fcntl.fcntl(f.fileno(), fcntl.F_GETFL)
								fcntl.fcntl(f.fileno(), fcntl.F_SETFL, fl | os.O_NONBLOCK)
							img_plot = plt.imshow(img_arr)
							img_plot.figure.canvas.mpl_connect('close_event', handle_close)
						else:
							img_plot.set_data(img_arr)
						_refresh_plot(img_plot, options.gui_timeout)
					else:
						sys.stdout.write(".")
						sys.stdout.flush()
					if y != _y:
						received_scanline_cnt += 1
						do_gui_update = ((received_scanline_cnt % options.gui_lines) == 0)
					y = _y
					x = 0
					p = 0
					buf = buf[(int_len * 5):]
					idx2 = buf.find(MAGIC_packed)
					if idx2 == -1:
						idx2 = len(buf)
					y, x, p = _fill_img(img_arr, bpp, y, x, p, buf[:idx2], do_gui_update)
					buf = buf[idx2:]
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
