#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  tcp_server.py
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

from __future__ import with_statement

import sys, threading, traceback, socket, SocketServer, time, select

from optparse import OptionParser

LISTEN_RETRY_INTERVAL = 5

class SendThread(threading.Thread):
    def __init__(self, client, limit=0, *args, **kwds):
        threading.Thread.__init__(self, *args, **kwds)
        self.client = client
        self.limit = limit
        self.setDaemon(True)
        self.continue_running = True
        self.add_event = threading.Event()
        self.queue = ""
        self.queue_lock = threading.RLock()
    #def start(self):
    #    super(SendThread, self).start()
    def get_lock(self):
        return self.queue_lock
    def get_queue_length(self):
        return len(self.queue)
    def stop(self):
        self.continue_running = False
        self.add_event.set()
    def add(self, msg):
        with self.queue_lock:
            if self.limit > 0 and len(self.queue) >= self.limit:
                return False
            self.queue += msg
            #sys.stdout.write("%s + %d\n" % (self.client.client_address, len(self.queue)))
            #sys.stdout.flush()
            self.add_event.set()
        return True
    def run(self):
        #print "SendThread running for:", self.client.client_address
        while self.continue_running:
            try:
                self.add_event.wait()
                
                while self.continue_running and len(self.queue) > 0:
                    ready_to_read, ready_to_write, in_error = select.select([],[self.client.request],[])
                    if self.client.request not in ready_to_write:
                        self.continue_running = False
                        break
                    
                    with self.queue_lock:
                        self.add_event.clear()
                        
                        sent = self.client.request.send(self.queue)
                        if sent <= 0:
                            print "Socket for %s was ready to send, but result was %s" % (self.client.client_address, sent)
                            continue
                        self.queue = self.queue[sent:]
                        #sys.stdout.write("%s - %d\n" % (self.client.client_address, len(self.queue)))
                        #sys.stdout.flush()
            except socket.error, (e, msg):
                if e == 9 or e == 32 or e == 104:  # Bad file descriptor, Broken pipe, Connection reset by peer
                    break
                else:
                    print "Socket error in SendThread for %s: %s" % (self.client.client_address, (e, msg))
            except Exception, e:
                print "Unhandled exception in SendThread for %s: %s" % (self.client.client_address, e)
        #print "SendThread exiting for:", self.client.client_address

class ThreadedTCPRequestHandler(SocketServer.StreamRequestHandler): # BaseRequestHandler
    # No __init__
    def setup(self):
        SocketServer.StreamRequestHandler.setup(self)
        if not self.server.silent: print "==> Connection from:", self.client_address#, "in thread", threading.currentThread().getName()
        self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
        self.send_thread = None
        if not self.server.blocking_mode:
            self.request.setblocking(0)
            self.send_thread = SendThread(self, self.server.send_limit)
            self.send_thread.start()
        with self.server.client_lock:
            self.server.clients.append(self)
        self.server.connect_event.set()
    def handle_data(self, data):
        # In init: self.buffer = ""
        #print "==> Received from", self.client_address, ":", data
        
        #cur_thread = threading.currentThread()
        #response = "%s: %s" % (cur_thread.getName(), data)
        #self.request.send(response)
        
        #self.buffer += data
        #lines = self.buffer.splitlines(True)
        #for line in lines:
        #    if line[-1] != '\n':
        #        self.buffer = line
        #        break
        #    line = line.strip()
        #    print "[%s] %s" % (self.client_address, line)
        #else:
        #    self.buffer = ""
        return True
    def handle(self):
        #buffer = ""
        while True:
            data = ""   # Initialise to nothing so if there's an exception it'll disconnect
            try:
                ready_to_read, ready_to_write, in_error = select.select([self.request],[],[])
                if self.request in ready_to_read:
                    data = self.request.recv(self.server.buffer_size)
                # For reference:
                #data = self.rfile.readline().strip()
            except socket.error, (e, msg):
                if e != 104 and e != 9:    # Connection reset by peer, Bad file descriptor
                    print "==> While receiving from", self.client_address, "-", e, msg
            if len(data) == 0:
                break
            
            if self.handle_data(data) == False:
                break
    def finish(self):
        if not self.server.silent: print "==> Disconnection from:", self.client_address
        if self.send_thread:
            self.send_thread.stop()
        with self.server.client_lock:
            self.server.clients.remove(self)
            if len(self.server.clients) == 0:
                self.server.connect_event.clear()
        try:
            SocketServer.StreamRequestHandler.finish(self)
        except socket.error, (e, msg):
            if e != 32: # Broken pipe
                print "==>", self.client_address, "-", msg
    def send(self, msg, try_same_thread=True, raise_exception=False):  # FIXME: log instead of print
        if self.send_thread is None:
            self.request.send(msg)
            return True
        
        with self.send_thread.get_lock():
            if try_same_thread == False or self.send_thread.get_queue_length() > 0:
                if not self.send_thread.add(msg):
                    print "Send buffer full for %s (dropping %d bytes)" % (self.client_address, len(msg))
                return False
            
            try:
                ready_to_read, ready_to_write, in_error = select.select([],[self.request],[],0)
                if self.request in ready_to_write:
                    sent = self.request.send(msg)
                    if sent <= 0:
                        print "Socket for %s was ready to send, but result was %s" % (self.client_address, sent)
                        sent = 0
                    elif sent == len(msg):
                        return True
                    msg = msg[sent:]
                if not self.send_thread.add(msg):
                    print "Send buffer full for %s (dropping %d bytes)" % (self.client_address, len(msg))
            except socket.error, (e, msg):
                if e != 32: # Broken pipe (silently ignore)
                    print "Socket error when sending to %s: %s" % (self.client_address, (e, msg))
                if raise_exception:
                    raise
            except Exception, e:
                print "Unhandled exception in send for %s: %s" % (self.client_address, e)
                if raise_exception:
                    raise
            return False

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    def __init__(self, address, request_handler=ThreadedTCPRequestHandler, buffer_size=1024*4*4, send_limit=0, blocking_mode=False, silent=False, *args, **kwds):
        self.address = address
        self.request_handler = request_handler
        self.buffer_size = buffer_size
        self.send_limit = send_limit
        self.blocking_mode = blocking_mode
        self.silent = silent
        
        self.server_thread = None
        self.client_lock = threading.Lock()
        self.clients = []
        self.connect_event = threading.Event()
        self.keep_connecting = True
        self.allow_reuse_address = True
    def start(self, retry=False, wait=5, log=None):
        if self.server_thread:
            return
        while self.keep_connecting:
            try:
                SocketServer.TCPServer.__init__(self, self.address, self.request_handler)
                #ip, port = self.server_address
                break
            except socket.error, (e, msg):
                if retry and ((e == 98) or (e == 48)): # Address already in use   (both)
                    if log: log(e, msg)
                    time.sleep(wait)
                    continue
                raise
        self.server_thread = threading.Thread(target=self.serve_forever)
        self.server_thread.setDaemon(True)
        self.server_thread.start()
    def send(self, data, log=None):
        with self.client_lock:
            for client in self.clients:
                try:
                    if self.blocking_mode:
                        client.wfile.write(data)
                    else:
                        client.send(data)
                except socket.error, (e, msg):
                    if log: log(client, e, msg)
    def shutdown(self, disconnect_clients=False, log=None):
        self.keep_connecting = False
        if self.server_thread:
            SocketServer.TCPServer.shutdown(self)
        if disconnect_clients:
            self.disconnect_clients(log)
    def disconnect_clients(self, log=None):
        with self.client_lock:
            #if len(server.clients) > 0:
            #    print "Disconnecting clients..."
            for client in self.clients:
                if log: log(client)
                client.request.shutdown(socket.SHUT_RDWR)
                client.request.close()

def main():
    parser = OptionParser(usage="%prog: [options] <destination>[:port]")
    
    parser.add_option("-p", "--port", type="int", default=12876, help="server listen port [default=%default]")
    parser.add_option("-P", "--upstream-port", type="int", default=12876, help="upstream server port [default=%default]")
    parser.add_option("-b", "--buffer-size", type="int", default=1024*4, help="receive buffer size [default=%default]")
    parser.add_option("-l", "--listen", action="store_true", default=False, help="listen on a socket instead of connecting to an upstream server [default=%default]")
    parser.add_option("-s", "--sleep", type="float", default=1.0, help="server listen port [default=%default]")
    parser.add_option("-L", "--limit", type="int", default=-1, help="async send buffer limit (-1: unlimited) [default=%default]")
    parser.add_option("-B", "--blocking-send", action="store_true", default=False, help="disable async send thread [default=%default]")
    
    (options, args) = parser.parse_args()
    
    if not options.listen and len(args) < 1:
        print "Supply destination address"
        return
    
    destination_addr = None
    if len(args) >= 1:
        destination_addr = args[0]
        idx = destination_addr.find(':')
        if idx > -1:
            try:
                options.upstream_port = int(destination_addr[idx+1:])
            except Exception, e:
                print "Failed to parse destination address port:", e
                return
            destination_addr = destination_addr[:idx]
    elif options.listen:
        destination_addr = "0.0.0.0"
    
    destination = (destination_addr, options.upstream_port)
    HOST, PORT = "", options.port   # FIXME: Choose interface e.g. "localhost"
    server = None
    
    print "==> Starting TCP server on port:", PORT
    
    try:
        server = ThreadedTCPServer((HOST, PORT), buffer_size=options.buffer_size, blocking_mode=options.blocking_send, send_limit=options.limit)
        
        def _log_listen_retry(e, msg):
            print "    Socket error:", msg
            if e == 98:
                print "    Waiting, then trying again..."
        
        server.start(retry=True, wait=LISTEN_RETRY_INTERVAL, log=_log_listen_retry)
        
        print "==> TCP server running in thread:", server.server_thread.getName()
        
        s, l = None, None
        
        # For stdin:
        # Also consider "-u" unbuffered I/O option for Python
        #data = sys.stdin.read(1)
        # Snippet:
        #fd = sys.stdin.fileno()
        #default_attr = termios.tcgetattr(sys.stdin)
        #tty.setraw(fd)
        
        if options.listen:
            l = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listen_addr = (destination_addr, options.upstream_port)
            
            print "Starting upstream server on:", listen_addr
            
            while True:
                try:
                    l.bind(listen_addr)
                except socket.error, (e, msg):
                    print "    Socket error:", msg
                    if e == 98:
                        print "    Waiting, then trying again..."
                        time.sleep(LISTEN_RETRY_INTERVAL)
                        continue
                    return
                break
            
            l.listen(1)
            
            print "Listening on:", listen_addr
        
        while True:
            if s:
                try:
                    
                    s.shutdown(socket.SHUT_RDWR)
                    s.close()
                except Exception, e:
                    #print "Exception while closing upstreams socket:", e
                    pass
                
                s = None
            
            if options.listen:
                print "Waiting for incoming upstream connection..."
                
                try:
                    s, addr = l.accept()
                
                    print "Accepted connection from:", addr
                except socket.error, (e, msg):
                    print "Exception while in accept:", (e, msg)
                    break
                # Fall through
            elif destination_addr != "-":
                print "Connecting to:", destination

                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect(destination)

                    print "Connected to upstream server"
                except socket.error, (e, msg):
                    if e == 111 or e == 113: # Connection refused, No route to host
                        print "Connection refused. Re-trying..."
                        time.sleep(options.sleep)
                        continue
                    
                    print "Exception while connecting:", (e, msg)
                    break
                # Fall through
            
            while True:
                try:
                    msg_str = ""
                    
                    # Manual entry
                    #msg_str = raw_input()
                    
                    if s:
                        msg_str = s.recv(options.buffer_size)
                        if len(msg_str) == 0:
                            break
                    else:
                        msg_str = sys.stdin.readline()
                    
                    if len(msg_str) == 0:
                        continue
                    
                    def _log_send_error(client, e, msg):
                        if e != 32: # Broken pipe
                            print "==> While sending to", client.client_address, "-", e, msg
                    server.send(msg_str, log=_log_send_error)
                except socket.error, (e, msg):
                    print "Socket error %s: %s" % (e, msg)
    except KeyboardInterrupt:
        pass
    except Exception, e:
        print "Unhandled exception:", e
        print traceback.format_exc()
    
    try:
        if server:
            print "Shutting down..."
            
            def _log_shutdown(client):
                print "Disconnecting client:", client.client_address
            
            server.shutdown(True, log=_log_shutdown)
    except Exception, e:
        print "Unhandled exception during shutdown:", e

if __name__ == '__main__':
    main()
