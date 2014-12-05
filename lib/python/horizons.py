#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  horizons.py
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

# TO DO
# * Step back sleep*window to calculate doppler delta for single mode

import sys, time, struct, datetime, threading
import curses
import tzlocal
import numpy
from dateutil import parser as date_parser
from optparse import OptionParser

_START = "$$SOE"
_END = "$$EOE"

class horizons_thread(threading.Thread):
	def __init__(self, input_path, freq, callback, sleep=1.0, auto_start=True, *args, **kwds):	# +ve: downlink, -ve: uplink
		threading.Thread.__init__(self, *args, **kwds)
		self.setDaemon(True)
		self.keep_running = True
		self.callback = callback
		self.sleep = sleep
		self.hint = 0
		self.direction = 1
		self.set_freq(freq)
		self.stop_event = threading.Event()
		print "Reading \"%s\"" % (input_path)
		self.h = horizons(input_path)
		if auto_start:
			self.start()
	def start(self):
		print "Starting..."
		threading.Thread.start(self)
	def stop(self):
		if not self.keep_running:
			return
		print "Stopping..."
		self.keep_running = False
		self.stop_event.wait()
		print "Stopped"
	def __del__(self):
		print "DTOR"
	def set_freq(self, freq):
		if freq < 0:
			self.direction = -1
			freq = -freq
		self.freq = freq
	def get(self, freq=None, now_utc=None, hint=None, safe=False):
		direction = 1
		if freq is None:
			freq = self.freq
			direction = self.direction
		else:
			if freq < 0:
				direction = -1
				freq = -freq
		
		if now_utc is None:
			now_utc = datetime.datetime.utcnow()
		
		if hint is None:
			hint = self.hint
		
		res = self.h.get(now_utc, hint)
			
		if res is None:
			if safe:
				#print (None, freq)
				return (None, freq)
			#print res
			return res
		
		hint, deldot_now, delta_now, ra_now, decl_now, frac = res
		
		c = 299792458.0
		f_doppler = c / ((c + (direction * deldot_now * 1000)) / freq)
		
		#print (res, f_doppler), f_doppler-freq
		return (res, f_doppler)
		
	def run(self):
		#time.sleep(self.sleep)	# HACK: for UI update
		
		while self.keep_running:
			res = self.get()
			
			if res is None:
				break
			#print res, res[1]-self.freq
			res, f_doppler = res
			self.hint, deldot_now, delta_now, ra_now, decl_now, frac = res
			
			try:
				self.callback(f_doppler)
			except Exception, e:
				print "While executing horizons callback:", e
			
			time.sleep(self.sleep)
		
		self.stop_event.set()

def format_freq(f, decimals=None, units=True, extra=""):
	unit = ''
	_f = abs(f)
	if _f >= 1e9:
		f /= 1e9
		unit = 'G'
	elif _f >= 1e6:
		f /= 1e6
		unit = 'M'
	elif _f >= 1e3:
		f /= 1e3
		unit = 'k'
	if decimals is None:
		fmt = "%%%sf" % (extra)
	else:
		fmt = "%%%s.%df" % (extra, decimals)
	freq_str = fmt % f
	if units:
		freq_str += " %sHz" % (unit)
	return freq_str

class horizons():
	def __init__(self, input_path=None, *args, **kwds):
		#self.input_path = input_path
		if input_path is not None:
			self.parse(input_path)
	
	def parse(self, input_path):
		self.data = []
		
		with open(input_path) as f:
			lines = f.readlines()
			in_data = False
			for line in lines:
				line = line.strip()
				if line == _START:
					in_data = True
					continue
				elif line == _END:
					break
				if not in_data:
					continue
				#"2014-May-23 00:00 A   07 34 06.09 +21 55 30.0   n.a.   n.a. 0.11457166654073  -3.2683587  50.1314 /T 124.5182"
				parts = line.split()
				line_time_str = parts[0] + " " + parts[1]
				line_time = date_parser.parse(line_time_str)
				#print line_time
				try:
					i = int(parts[2])
					parts = parts[:2] + [''] + parts[2:]
				except:
					pass
				
				deldot = float(parts[12])
				#print deldot
				delta = float(parts[11])
				ra = float(parts[3]) + (float(parts[4]) / 60.0) + (float(parts[5]) / 3600.0)
				decl = float(parts[6]) + (float(parts[7]) / 60.0) + (float(parts[8]) / 3600.0)
				
				self.data += [{'time':line_time, 'deldot':deldot, 'delta':delta, 'ra':ra, 'decl':decl}]
		
		return len(self.data)
	
	def get_line_count(self): return len(self.data)
	
	def get(self, now_utc, hint=0):
		last = None
		frac = None
		for i in range(hint, len(self.data)):
			d = self.data[i]
			
			if last is not None:
				if now_utc >= last['time'] and now_utc < d['time']:
					diff = d['time'] - last['time']
					now_diff = now_utc - last['time']
					
					frac = now_diff.total_seconds() / diff.total_seconds()
					
					def _interpolate(key, now, prev, factor):
						return prev[key] + ((now[key] - prev[key]) * factor)
					
					deldot_now = _interpolate('deldot', d, last, frac)
					delta_now  = _interpolate('delta', d, last, frac)
					ra_now     = _interpolate('ra', d, last, frac)
					decl_now   = _interpolate('decl', d, last, frac)
					
					return ((i - 1), deldot_now, delta_now, ra_now, decl_now, frac)
			
			last = d
		
		return None

def main():
	parser = OptionParser(usage="%prog: [options] <input file>")	#option_class=eng_option, 
	
	parser.add_option("-u", "--uplink", type="string", default="", help="uplink frequencies (Hz) [default=%default]")
	parser.add_option("-d", "--downlink", type="string", default="", help="downlink frequencies (Hz) [default=%default]")
	parser.add_option("-i", "--interval", type="float", default="1.0", help="sleep time (s) [default=%default]")
	parser.add_option("-w", "--window", type="int", default="10", help="averaging window size [default=%default]")
	parser.add_option("-t", "--time", type="string", default="", help="start time [default=%default]")
	parser.add_option("-f", "--time-format", type="string", default="%Y-%m-%d %H:%M:%S", help="time format [default=%default]")
	parser.add_option("-o", "--time-offset", type="float", default=0, help="manual time offset (s) [default=%default]")
	parser.add_option("-z", "--time-zone", type="float", default=None, help="manual time zone offset (hr) [default=%default]")
	parser.add_option("-s", "--single", action="store_true", default=False, help="one calculation [default=%default]")
	
	(options, args) = parser.parse_args()
	
	if len(args) < 1:
		print "Supply input file"
		return 0
	
	uplink_freqs, downlink_freqs = [], []
	if len(options.uplink) > 0:
		uplink_freqs = map(float, options.uplink.split(','))
	if len(options.downlink) > 0:
		downlink_freqs = map(float, options.downlink.split(','))
	
	offset = None
	if options.time_zone is not None:
		offset = datetime.timedelta(hours=options.time_zone)
	
	custom_start_time = None
	if len(options.time) > 0:
		try:
			l = []
			if len(options.time_format) > 0:
				l += [options.time_format]
			custom_start_time = datetime.datetime.strptime(options.time, *l)
			custom_start_time += datetime.timedelta(seconds=options.time_offset)
			print "Starting at: %s (local)" % (custom_start_time)
			#raw_input()
		except Exception, e:
			print "Failed to parse start time: %s" % (options.time)
			print e
			return
	
	filename = args[0]
	print "Opening", filename
	
	h = horizons(filename)
	
	#print "Starting..."
	
	stdscr = curses.initscr()
	
	#curses.noecho()
	#curses.cbreak()
	#stdscr.keypad(1)
	#curses.nl / curses.nonl
	#stdscr.deleteln()
	
	ex = None
	local_tz = tzlocal.get_localzone()
	
	uplink_freq_delta = [[]] * len(uplink_freqs)
	downlink_freq_delta = [[]] * len(downlink_freqs)
	
	prev_uplink_doppler_freq = [None] * len(uplink_freqs)
	prev_downlink_doppler_freq = [None] * len(downlink_freqs)
	
	local_start_time = None
	start_time = None
	if offset is None:
		offset = local_tz.utcoffset(datetime.datetime.now())
	
	hint = 0
	
	try:
		while True:
			stdscr.erase()
			
			if custom_start_time is None:
				#now = datetime.datetime.now()
				now_utc = datetime.datetime.utcnow()
				#offset = local_tz.utcoffset(now)
				#now_utc = now - offset
				now = now_utc + offset
			else:
				local_now = datetime.datetime.now()
				if local_start_time is None:
					local_start_time = local_now
				now = custom_start_time + (local_now - local_start_time)
				now_utc = now - offset
			
			if start_time is None:
				start_time = now
			
			run_time = now - start_time
			
			#print "Now:", now
			#print "UTC:", now_utc
			stdscr.addstr("UTC  : %s\n" % (now_utc))
			stdscr.addstr("Local: %s (%+.1f)\n" % (now, (offset.total_seconds()/3600)))
			stdscr.addstr("Run  : %s\n" % (run_time))
			stdscr.addstr("\n")
			
			res = h.get(now_utc, hint)
			
			if res is None:
				ex = "Current time is outside range of input file"
				break
			
			hint, deldot_now, delta_now, ra_now, decl_now, frac = res
			line_cnt = hint + 1
			
			stdscr.addstr("Lines: %d/%d (%d left)\n" % (line_cnt, h.get_line_count(), (h.get_line_count() - line_cnt)))
			stdscr.addstr("\n")
			
			stdscr.addstr("Speed (km/s) : %.7f\n" % (deldot_now))
			stdscr.addstr("Speed (m/s)  : %.7f\n" % (deldot_now * 1000))
			stdscr.addstr("Speed (km/hr): %.7f\n" % (deldot_now * 3600))
			stdscr.addstr("\n")
			
			au_km = 149597870.7
			dist_km = delta_now * au_km
			stdscr.addstr("Dist (AU): %.14f\n" % (delta_now))
			stdscr.addstr("Dist (km): %.6f\n" % (dist_km))
			stdscr.addstr("\n")
			
			c = 299792458.0
			lt = dist_km * 1000.0 / c
			stdscr.addstr("Light time (one-way): %f s\n" % (lt))
			stdscr.addstr("Light time (two-way): %f s\n" % (lt*2))
			stdscr.addstr("\n")
			
			stdscr.addstr("R.A.:  %.10f\n" % (ra_now))
			stdscr.addstr("Decl: %+.10f\n" % (decl_now))
			stdscr.addstr("(adjusted for light time)\n")
			stdscr.addstr("\n")
			
			decimals = 9
			
			if len(downlink_freqs) > 0:
				stdscr.addstr("Downlink frequencies:\n\n")
				cnt = 0
				for f in downlink_freqs:
					f_doppler = c / ((c + (deldot_now * 1000)) / f)
					f_doppler_diff = f_doppler - f
					f_doppler_diff_prev = prev_downlink_doppler_freq[cnt]
					f_ave_doppler_delta = 0.0
					if f_doppler_diff_prev is not None:
						f_doppler_diff_delta = f_doppler_diff - f_doppler_diff_prev
						downlink_freq_delta[cnt] += [f_doppler_diff_delta]
						if len(downlink_freq_delta[cnt]) > options.window:
							downlink_freq_delta[cnt] = downlink_freq_delta[cnt][1:]
						f_ave_doppler_delta = numpy.average(downlink_freq_delta[cnt])
					stdscr.addstr("%s: %s (%s @ %s/sec, %s/min)\n" % (
						format_freq(f, decimals=decimals),
						format_freq(f_doppler, decimals=decimals),
						format_freq(f_doppler_diff, extra="+"),
						format_freq(f_ave_doppler_delta, extra="+"),
						format_freq(f_ave_doppler_delta * 60.0, extra="+")
					))
					prev_downlink_doppler_freq[cnt] = f_doppler_diff
					cnt += 1
				stdscr.addstr("\n")
			
			if len(uplink_freqs) > 0:
				stdscr.addstr("Uplink frequencies:\n\n")
				cnt = 0
				for f in uplink_freqs:
					f_doppler = c / ((c - (deldot_now * 1000)) / f)
					f_doppler_diff = f_doppler - f
					f_doppler_diff_prev = prev_uplink_doppler_freq[cnt]
					f_ave_doppler_delta = 0.0
					if f_doppler_diff_prev is not None:
						f_doppler_diff_delta = f_doppler_diff - f_doppler_diff_prev
						uplink_freq_delta[cnt] += [f_doppler_diff_delta]
						if len(uplink_freq_delta[cnt]) > options.window:
							uplink_freq_delta[cnt] = uplink_freq_delta[cnt][1:]
						f_ave_doppler_delta = numpy.average(uplink_freq_delta[cnt])
					stdscr.addstr("%s: %s (%s @ %s/sec, %s/min)\n" % (
						format_freq(f, decimals=decimals),
						format_freq(f_doppler, decimals=decimals),
						format_freq(f_doppler_diff, extra="+"),
						format_freq(f_ave_doppler_delta, extra="+"),
						format_freq(f_ave_doppler_delta * 60.0, extra="+")
					))
					prev_uplink_doppler_freq[cnt] = f_doppler_diff
					cnt += 1
				stdscr.addstr("\n")
			
			stdscr.refresh()
			
			if options.single:
				stdscr.addstr("Press any key to exit...")
				stdscr.refresh()
				stdscr.getch()
				break
			
			time.sleep(options.interval)
	except KeyboardInterrupt:
		pass
	except Exception, e:
		ex = e
	
	stdscr.erase()
	stdscr.refresh()
	
	curses.nocbreak()
	stdscr.keypad(0)
	curses.echo()
	curses.endwin()
	
	if ex:
		print "Unhandled exception:", ex
	
	return 0

if __name__ == '__main__':
	main()
