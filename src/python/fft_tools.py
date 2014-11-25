#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  fft_tools.py
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

import numpy
import math

import sys

def mirror_fft(data):
    pos_len = (len(data) + 1) / 2
    pos = data[:pos_len]
    neg = data[len(data) - pos_len:]
    return numpy.concatenate((neg, pos))

# Assumes input values [0,1]
def calc_fft(samps, num_bins=None, log_scale=True, step=1, window=numpy.hamming, pad=True, adjust=True, verbose=False):  # FIXME: step (when it was floating point, for more flexible overlap)
    if num_bins is None:
        num_bins = len(samps)
    num_ffts = len(samps)/num_bins
    point_count = num_ffts * num_bins
    if verbose: print "Processing %d FFTs" % (num_ffts / step)
    left_over = len(samps) - point_count
    if point_count != len(samps):
        if not pad:
            if verbose: print "Skipping %d tail samples for FFT" % (left_over)
    
    fft_sum = numpy.zeros(num_bins)
    fft_max = numpy.zeros(num_bins)
    fft_min = numpy.ones(num_bins)
    if window is None:
        #window_points = numpy.ones(num_bins)
        window_points = None
    else:
        window_points = window(num_bins)
    
    if pad:
        pad_amount = num_bins - left_over
        if isinstance(samps, list):
            samps += [0]*pad_amount
        elif isinstance(samps, numpy.ndarray):
            samps = numpy.concatenate((samps, numpy.zeros(pad_amount)))
        else:
            raise Exception("Cannot pad unknown type '%s': %s" % (type(samps), str(samps)))
    
    cnt = 0
    for i in range(0, num_ffts, step):
        cnt += 1
        data = numpy.array(samps[i*num_bins:i*num_bins + num_bins])
        if window_points is not None:
            data *= window_points
        fft = numpy.fft.fft(data)
        fft = mirror_fft(fft)
        fft = numpy.abs(fft)
        
        fft = (fft * fft)
        fft_sum += fft
        fft_min = numpy.minimum(fft, fft_min)
        fft_max = numpy.maximum(fft, fft_max)
        
        #sys.stdout.write("%d " % (i))
        #sys.stdout.flush()
    
    #print
    
    fft_avg = fft_sum / float(cnt)
    
    if log_scale:
        if verbose:
            sys.stdout.write("Running logarithm...")
            sys.stdout.flush()
        adjust_amount = 0.0
        if adjust:
            ref_scale = 2
            adjust_amount =(-20.0 * math.log10(num_bins)                # Adjust for number of bins
                            -20.0 * math.log10(ref_scale/2))            # Adjust for reference scale
            if window_points is not None:
                window_power = sum(map(lambda x: x*x, window_points))
                adjust_amount += (-10.0 * math.log10(window_power/num_bins))   # Adjust for windowing loss
        
        fft_avg = (10.0 * numpy.log10(fft_avg)) + adjust_amount
        fft_max = (10.0 * numpy.log10(fft_max)) + adjust_amount
        fft_min = (10.0 * numpy.log10(fft_min)) + adjust_amount
        
        if verbose:
            print "done."
    
    return (cnt, fft_avg, fft_min, fft_max)
