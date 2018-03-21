#!/usr/bin/env python
# 
# Copyright 2018 Balint Seeber
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import os, struct, datetime
import numpy

class InputFile():
	def __init__(self, path, format_hint=None, samp_rate_hint=None, freq_hint=None):
		self._path = path
		self._format_hint = format_hint
		self._samp_rate_hint = samp_rate_hint
		self._freq_hint = freq_hint

		self._samp_rate = None
		self._format = None
		self._data_offset = 0 # Bytes
		self._length = 0 # Bytes
		self._item_size = 0
		self._item_factor = 1
		self._f = None
		self._freq = None
		self._time_start = None
		self._time_end = None
		self._file_type = None

		self._open()

	def _open(self):
		fileinfo = os.stat(self._path)

		manual_end_time = False
		manual_start_time = False

		with open(self._path, 'rb') as f:
			RIFF = f.read(4)
			if RIFF == "RIFF":
				self._file_type = RIFF

				self._freq = self._freq_hint

				riff_size, = struct.unpack("<I", f.read(4))
				# print riff_size, hex(riff_size)
				# FIXME: Check riff_size
				WAVE = f.read(4)
				# print WAVE
				if WAVE == "WAVE":
					self._file_type = WAVE

					while True:
						chunk_id = f.read(4)
						if chunk_id == "":
							break
						chunk_size, = struct.unpack("<I", f.read(4))
						# print chunk_id, chunk_size, hex(chunk_size)
						file_pos = f.tell()

						if chunk_id == "fmt ":
							WAVEFORMATEX_format = "<HHIIHH"
							WAVEFORMATEX_size = struct.calcsize(WAVEFORMATEX_format)
							format, channels, samples_per_sec, avg_bytes_per_sec, block_align, bits_per_sample = struct.unpack(WAVEFORMATEX_format, f.read(WAVEFORMATEX_size))
							# print "format: {}, channels: {}, samples_per_sec: {}, avg_bytes_per_sec: {}, block_align: {}, bits_per_sample: {}".format(format, channels, samples_per_sec, avg_bytes_per_sec, block_align, bits_per_sample)

							assert(format == 1)
							assert(channels == 2)

							self._samp_rate = samples_per_sec

							if bits_per_sample == 16:
								self._format = numpy.dtype('i2') # FIXME: Why doesn't int16 work here? (.itemsize)
							else:
								raise Exception("Unhandled bits-per-sample: {}".format(bits_per_sample))

						elif chunk_id == "auxi":
							SYSTEMTIME_format = "<HHHHHHHH" # year, month, day_of_week, day, hour, minute, second, millisecond
							SYSTEMTIME_size = struct.calcsize(SYSTEMTIME_format)
							time_start = struct.unpack(SYSTEMTIME_format, f.read(SYSTEMTIME_size))
							time_end = struct.unpack(SYSTEMTIME_format, f.read(SYSTEMTIME_size))
							freq1, = struct.unpack("<I", f.read(4))
							f.read(24) # Padding
							freq2, = struct.unpack("<I", f.read(4)) # Same as freq1
							# print time_start
							# print time_end
							# print freq1, freq2

							assert(freq1 == freq2)

							self._freq = float(freq1)

							self._time_start = datetime.datetime(time_start[0], time_start[1], time_start[3], time_start[4], time_start[5], time_start[6], 1000 * time_start[7])
							self._time_end = datetime.datetime(time_end[0], time_end[1], time_end[3], time_end[4], time_end[5], time_end[6], 1000 * time_end[7])

						elif chunk_id == "data":
							self._data_offset = file_pos
							# FIXME: Check chunk_size

						else:
							pass

						f.seek(file_pos + chunk_size, 0)
				else:
					raise Exception("Unknown RIFF type: {}".format(WAVE))
			else:
				self._file_type = "RAW"
				head, tail = os.path.split(self._path)
				if tail.startswith("gqrx_"): # gqrx_YYYYMMDD_HHMMSS_Hz_sps_fc.raw
					head, tail = os.path.splitext(tail)
					parts = head.split("_")
					ymd = parts[1]
					hms = parts[2]
					self._time_start = datetime.datetime(int(ymd[0:4]), int(ymd[4:6]), int(ymd[6:8]), int(hms[0:2]), int(hms[2:4]), int(hms[4:6]))
					self._freq = float(parts[3])
					self._samp_rate = float(parts[4])
					if parts[5] == "fc":
						self._format = numpy.dtype('c8')
					manual_end_time = True
				else: # r(Msps)_f(MHz)_g(gain).sc16
					head, tail = os.path.splitext(tail)
					tail = tail.lower()
					if tail == ".sc16":
						self._format = numpy.dtype('i2')
					parts = head.split("_")
					for part in parts:
						p = part[0].lower()
						v = part[1:]
						if p == "f":
							self._freq = float(v) * 1e6
						elif p == "r":
							self._samp_rate = float(v) * 1e6
					self._time_end = datetime.datetime.fromtimestamp(fileinfo.st_mtime)
					manual_start_time = True

				if self._samp_rate is None:	
					self._samp_rate = self._samp_rate_hint
				if self._format is None:
					self._format = self._format_hint
				if self._freq is None:
					self._freq = self._freq_hint

		# FIXME: Timing file

		self._item_factor = 1
		if self._format is not None:
			if self._format == numpy.int16:
				self._item_factor = 2
			self._item_size = self._format.itemsize * self._item_factor

		self._length = fileinfo.st_size - self._data_offset

		if manual_start_time and self._time_end is not None:
			self._time_start = self._time_end - datetime.timedelta(seconds=self.duration())
		elif manual_end_time and self._time_start is not None:
			self._time_end = self._time_start + datetime.timedelta(seconds=self.duration())

	def __str__(self):
		return "{} ({} {}, {: >9} Hz, {: >9} samples, {: >5.1f} s, {} - {})".format(
			self._path,
			self._file_type,
			self._format,
			self._samp_rate,
			self.samples(),
			self.duration(),
			str(self._time_start)[:-3] if self._time_start is not None else "?",
			str(self._time_end)[:-3] if self._time_end is not None else "?",
		)

	def path(self):
		return self._path

	def samples(self):
		if self._item_size == 0:
			return 0
		return self._length / self._item_size

	def seek(self, offset):
		if self._f is None:
			return -1

		offset_bytes = offset * self._item_size
		if offset_bytes < 0:
			offset_bytes += self._length

		offset_bytes += self._data_offset
		self._f.seek(offset_bytes)
		return offset_bytes

	def tell(self):
		if self._f is None:
			return -1

		offset_bytes = self._f.tell()
		offset_bytes -= self._data_offset
		offset = offset_bytes / self._item_size
		return offset

	def read(self, length):
		if length <= 0:
			return ""

		if self._f is not None:
			self.open()

		return self._f.read(length * self._item_size)

	def memmap(self):
		if self._format is None:
			return None
		if (self._data_offset % self._format.itemsize) != 0:
			raise Exception("Cannot use memmap where data offset {} is not divisble by item size {}".format(self._data_offset, self._format.itemsize))
		return numpy.memmap(self._path, self._format, 'r')

	def data_offset(self, raw_item_size=False):
		if raw_item_size:
			if self._format is None:
				return None
			assert((self._format.itemsize * self._item_factor) == self._item_size)
			assert((self._data_offset % self._format.itemsize) == 0)
			return (self._data_offset / self._format.itemsize)

		assert((self._data_offset % self._item_size) == 0)
		return (self._data_offset / self._item_size)

	def open(self, offset=0):
		if self._f is None:
			self._f = open(self._path, "rb")
		# self._f.seek(self._data_offset)
		self.seek(offset)
		return self._f

	def close(self):
		if self._f is not None:
			self._f.close()

	def format(self):
		return self._format

	def type_code(self):
		if self._format is None:
			return None
		return self._format.str.strip("<>")

	def sample_rate(self):
		return self._samp_rate

	def duration(self):
		if self._samp_rate is None:
			return None
		return 1.*self.samples() / self._samp_rate

	def freq(self):
		return self._freq

	def item_size(self):
		return self._item_size

	def time_end(self):
		return self._time_end

	def time_start(self):
		return self._time_start

	def item_factor(self):
		return self._item_factor

	def time_start(self):
		return self._time_start

	def time_end(self):
		return self._time_end
