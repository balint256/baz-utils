#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  run_remote.py
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

import sys, subprocess, os, signal, time

#def signal_term_handler(signal, frame):
	##print 'got SIGTERM'
#	return

def run_remote(remote_host, ignore=[], screen=False, x_forwarding=True, shell="bash"):	#, ssh_options=[]
	if 'REMOTE_RUN' in os.environ:
		#print "Launched remotely:", os.environ['REMOTE_RUN']
		return False
	
	ignore = map(str.lower, ignore)
	base_name = os.path.basename(sys.argv[0])
	if base_name.lower() in ignore:
		return False
	
	#signal.signal(signal.SIGTERM, signal_term_handler)
	#print "Installed signal handler"
	
	#print "Running inside:", sys.argv[0]
	#print "Remote host:", remote_host
	
	#print "Copying..."
	remote_copy = ["scp", "-q", sys.argv[0], remote_host]
	
	#print remote_copy
	p = subprocess.Popen(remote_copy)
	p.wait()
	
	#print "Running..."
	f = os.path.basename(sys.argv[0])
	idx = remote_host.find(':')
	if idx > -1:
		rh = remote_host[:idx]
		f = remote_host[idx+1:] + '/' + f
	else:
		rh = remote_host
	
	ssh_options = []
	if x_forwarding:
		ssh_options += ["-X"]
	
	if screen:
		#remote_run = ["ssh", "-t"] + ssh_options + [rh, "REMOTE_RUN=\""+sys.argv[0]+"\" screen -m \""+f+"\""]
		remote_run = ["ssh", "-t"] + ssh_options + [rh, "REMOTE_RUN=\""+sys.argv[0]+"\" screen -m "+shell+" -c -- \\\""+f+"\\\""]
	else:
		remote_run = ["ssh"] + ssh_options + [rh, shell, "-i", "-c", "--", "\"REMOTE_RUN=\\\""+sys.argv[0]+"\\\" \\\""+f+"\\\"\""]
	
	#print remote_run
	p = subprocess.Popen(remote_run)
	#print "SSH running"
	
	#print __file__
	subprocess.Popen(["python", __file__, str(os.getpid()), str(p.pid)])
	
	p.wait()
	
	#print "Exiting..."
	sys.exit(0)
	return True

def main():
	if len(sys.argv) < 3:
		return
	
	local_pid = int(sys.argv[1])
	ssh_pid = int(sys.argv[2])
	
	#print "Local PID:", local_pid
	#print "SSH PID:", ssh_pid
	
	pids = [local_pid, ssh_pid]
	keep_running = True
	exited_pid = None
	
	while keep_running:
		for pid in pids:
			try:
				os.kill(pid, 0)
			except OSError:	# This will not detect a defunct process
				exited_pid = pid
				#print "PID %d exited" % (pid)
				keep_running = False
				break
			else:
				try:
					ps_list = subprocess.check_output(["ps", "-a", "-o", "state,pid"]).split('\n')
					for ps in ps_list:
						if len(ps) == 0: continue
						if ps[0] == 'Z':
							parts = ps.split()
							if int(parts[1]) == pid:
								exited_pid = pid
								#print "Zombie process detected:", pid
								keep_running = False
								break
				except Exception, e:
					print e
		
		time.sleep(1.0)	# MAGIC
	
	if exited_pid == local_pid:
		try:
			os.kill(ssh_pid, 0)
		except OSError:
			pass
		else:
			#print "Closing SSH..."
			try:
				os.kill(ssh_pid, 15)	# SIGTERM
				#print "SSH closed"
			except:
				pass
	
	return 0

if __name__ == '__main__':
	main()
