#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  img_tx.py
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

import Image
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import numpy as np

def main():
	parser = OptionParser(usage="%prog: [options] <destination address> [input image]")
	
	parser.add_option("-d", "--delay", type="int", default=0, help="delay between scanlines (ms) [default=%default]")
	parser.add_option("-r", "--repeat", action="store_true", default=False, help="repeat transmission")
	parser.add_option("-p", "--port", type="int", default=12345, help="port [default=%default]")
	parser.add_option("-v", "--view", action="store_true", default=False, help="view image before transmission")
	parser.add_option("-P", "--pipe", action="store_true", default=False, help="use a pipe instead of a socket [default=%default]")
	parser.add_option("-B", "--transport-buffer-size", type="int", default=1, help="request transport buffer size [default=%default]")
	
	(options, args) = parser.parse_args()
	
	options.delay /= 1000.0
	
	if len(args) < 1:
		if options.pipe:
			print "Supply pipe name"
		else:
			print "Supply destination address"
		return
	
	image_filename = None
	destination_addr = args[0]
	if not options.pipe:
		if len(args) > 1:
			image_filename = args[1]
		idx = destination_addr.find(':')
		if idx > -1:
			options.port = int(destination_addr[idx+1:])
			destination_addr = destination_addr[:idx]
	
	if image_filename is not None:
		print "Opening:", image_filename
		img = Image.open(image_filename)
		#img_arr = mpimg.imread(image_filename)
	else:
		print "Using Lena"
		import scipy.misc as misc
		lena = misc.lena()
		print lena.shape
		size = (lena.shape[0], lena.shape[1])
		lena = lena.reshape((lena.shape[0]*lena.shape[1],1))
		buf = "".join(map(lambda x: chr(x), lena))
		img = Image.frombuffer("L", size, buf, 'raw', "L", 0, 1)
	
	print "Size:", img.size
	print "Mode:", img.mode
	print "Format:", img.format
	
	img_data = list(img.getdata())
	
	img_arr = np.asarray(img_data)
	img_arr = img_arr.reshape(img.size)
	
	if options.view:
		imgplot = plt.imshow(img_arr)
		plt.show()
	
	MAGIC = 0xFEDCBA98
	img_width = img.size[0]
	img_height = img.size[1]
	bpp = 1
	try:
		it = iter(img_data[0])
		bpp = len(img_data[0])
	except:
		pass
	print "BPP:", bpp
	MAGIC_packed = struct.pack("I", MAGIC)
	
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
		continue_running = True
		while continue_running and (cnt == 0 or options.repeat):
			sys.stdout.write("Sending image")
			sys.stdout.flush()
			for y in range(img_height):
				scanline_start = y * img_width
				scanline = img_data[scanline_start:(scanline_start+img_width)]
				if bpp > 1:
					scanline = [item for sublist in scanline for item in sublist]
				scanline_packed = ("".join(map(lambda x: chr(x), scanline))).replace(MAGIC_packed, MAGIC_packed + struct.pack("i", 0))
				buf = struct.pack("Iiiii", MAGIC, img_height, img_width, bpp, y)
				buf += scanline_packed
				if s:
					try:
						s.send(buf)
					except socket.error, (e, msg):
						if e == 104 or e == 32:	# Connection reset by peer, Broken pipe
							continue_running = False
							break
						raise
				if f:
					f.write(buf)
				sys.stdout.write(".")
				sys.stdout.flush()
				if options.delay > 0.0:
					time.sleep(options.delay)
			print "done!"
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
