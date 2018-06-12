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

import sys, math

import numpy

# Assumes normalised input values [-1,1]
def calc_fft(samps, num_bins=None, log_scale=True, step=1, window=numpy.hamming, pad=True, adjust=True, verbose=False, ref_scale=2.0):#, real=False):  # FIXME: step (when it was floating point, for more flexible overlap)
    if len(samps) == 0:
        return (0, numpy.array([]), numpy.array([]), numpy.array([]))

    step = max(1, int(step))    # Stride (of 'num_bins') used in processing loop below

    if num_bins is None:
        num_bins = len(samps)

    num_ffts = len(samps)/num_bins  # If less 'samps' than 'num_bins', will zero pad

    left_over = len(samps) - (num_ffts * num_bins)
    if left_over > 0:
        if pad:
            if verbose: print("Padding %d tail samples for FFT" % (num_bins - left_over))
            num_ffts += 1
        else:
            if verbose: print("Skipping %d tail samples for FFT" % (left_over))

    num_ffts = max(1, num_ffts) # Might still be 0 if not padding
    total_transforms = 1 + ((num_ffts-1) / step)
    if verbose: print("Processing %d FFTs" % (total_transforms))

    fft_sum = numpy.zeros(num_bins)
    fft_max = numpy.zeros(num_bins)
    # fft_min = numpy.ones(num_bins)
    fft_min = None
    if window is None:
        #window_points = numpy.ones(num_bins)
        window_points = None
    else:
        window_points = window(num_bins)
    
    # if pad:
    #     pad_amount = num_bins - left_over
    #     if isinstance(samps, list):
    #         samps += [0]*pad_amount
    #     elif isinstance(samps, numpy.ndarray):
    #         samps = numpy.concatenate((samps, numpy.zeros(pad_amount)))
    #     else:
    #         raise Exception("Cannot pad unknown type '%s': %s" % (type(samps), str(samps)))
    
    cnt = 0
    for i in range(0, num_ffts, step):
        start_idx = i * num_bins
        end_idx = min(len(samps), start_idx + num_bins)
        data = numpy.array(samps[start_idx:end_idx])

        if window_points is not None:
            if len(data) == num_bins:
                data *= window_points
            else:
                data *= window(len(data))   # Shorter window

        fft = numpy.fft.fft(data, num_bins) # Will zero pad if 'len(data)' < 'num_bins'
        fft = numpy.fft.fftshift(fft)
        fft = numpy.abs(fft)
        
        fft = (fft * fft)
        fft_sum += fft
        if fft_min is None:
            fft_min = fft
        else:
            fft_min = numpy.minimum(fft, fft_min)
        fft_max = numpy.maximum(fft, fft_max)
        
        # if verbose: 
        #    print("%d:%d " % (cnt, i),)
        #    sys.stdout.flush()

        cnt += 1
    
    #if verbose: print
    
    if cnt > 0:
        fft_avg = fft_sum / float(cnt)
    
    if log_scale:
        if verbose:
            print("Running logarithm...",)
            sys.stdout.flush()

        adjust_amount = 0.0
        if adjust:
            adjust_amount =(-20.0 * math.log10(num_bins)     # Adjust for number of bins
                            -20.0 * math.log10(ref_scale/2)) # Adjust for reference scale

            if window_points is not None:
                window_power = sum(map(lambda x: x*x, window_points))
                adjust_amount += (-10.0 * math.log10(window_power/num_bins)) # Adjust for windowing loss
        
        # FIXME  We need to add 3dB to all bins but the DC bin
        fft_avg = (10.0 * numpy.log10(fft_avg)) + adjust_amount
        fft_max = (10.0 * numpy.log10(fft_max)) + adjust_amount
        fft_min = (10.0 * numpy.log10(fft_min)) + adjust_amount
        
        if verbose: print("done.")
    
    return (cnt, fft_avg, fft_min, fft_max)
