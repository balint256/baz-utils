#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  run_remote_test.py
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

try:
	import sys;
	import run_remote;
	if run_remote.run_remote('balint@syskill:Desktop') == True:
		sys.exit(0)
except Exception, e: pass

#exec("try:\n\timport sys; import run_remote;\n\tif run_remote.run_remote('balint@syskill:Desktop') == True: sys.exit(0)\nexcept Exception, e: pass")

def main():
	print "Hello!"
	return 0

if __name__ == '__main__':
	main()
