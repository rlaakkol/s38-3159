import errno
import socket
import select
import time

import logging; log = logging.getLogger('pubsub.udp')

class Socket (object):
    """
        UDP datagram-based socket interface, using python __call__ and __iter__ semantics.

        Passing nonblocking=True will result in __iter__ returning early once the socket would block.
        The object is select()'able, having a .fileno() method.
    """

    SIZE = 1500

    @classmethod
    def connect (cls, host, port, **opts):
        try:
            ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
        except socket.gaierror as error:
            log.error("%s:%s: %s", port, host, error)
            raise

        for family, type, proto, canonname, sockaddr in ai:
            log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
            
            sock = socket.socket(family, type, proto)
            sock.connect(sockaddr)

            return cls(sock, **opts)

    @classmethod
    def listen (cls, port, host=None, **opts):
        try:
            ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM, flags=socket.AI_PASSIVE)
        except socket.gaierror as error:
            log.error("%s:%s: %s", port, host, error)
            raise

        for family, type, proto, canonname, sockaddr in ai:
            log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
            
            sock = socket.socket(family, type, proto)
            sock.bind(sockaddr)

            return cls(sock, **opts)

    def __init__ (self, sock, nonblocking=None):
        self.sock = sock

        if nonblocking is not None:
            self.sock.setblocking(not nonblocking)

    def fileno (self):
        return self.sock.fileno()

    def __call__ (self, buf, addr=None):
        """
            Send buf, addr from socket.
        """

        if addr:
            self.sock.sendto(buf, addr)
        else:
            self.sock.send(buf)

    def __iter__ (self):
        """
            Yield buf, addr received from socket.
        """

        while True:
            try:
                # recv -> bytes, (sockaddr)
                buf, addr = self.sock.recvfrom(self.SIZE, socket.MSG_TRUNC)

            except socket.error as error:
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    # nonblocking
                    return
                else:
                    log.exception("recvfrom: %s", error)
                    raise
            
            if len(buf) > self.SIZE:
                log.warning("%s: truncated message from %s at %d/%d bytes", self, addrname(addr), self.SIZE, len(buf))
                continue
                
            yield buf, addr

    def sockname (self):
        """
            Socket local address as a human-readble string.
        """

        return sockname(self.sock)

    def peername (self):
        """
            Socket remote address as a human-readble string.
        """

        return peername(self.sock)

    def __str__ (self):
        try:
            sock_name = sockname(self.sock)

        except (socket.error, socket.gaierror) as ex:
            log.exception("%s", ex)
            sock_name = None

        try:
            peer_name = peername(self.sock)

        except socket.error as ex:
            if ex.errno == errno.ENOTCONN:
                # Transport endpoint is not connected
                pass
            else:
                log.exception("%s", ex)
                
            peer_name = None
            
        except socket.gaierror as ex:
            log.exception("%s", ex)
            peer_name = None

        return "{peername}{sockname}".format(
                peername    = ("<{peername}>".format(peername=peer_name) if peer_name else ''),
                sockname    = ("[{sockname}]".format(sockname=sock_name) if sock_name else ''),
        )

def addrname (addr):
    """
        Return a human-readable representation of the given socket address.
    """

    host, port = socket.getnameinfo(addr, socket.NI_DGRAM | socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)
    
    return "{host}:{port}".format(host=host, port=port)

def sockname (sock):
    """
        Return a human-readable representation of the socket local address.
    """

    return addrname(sock.getsockname())
 
def peername (sock):
    """
        Return a human-readable representation of the socket remote address.
    """

    return addrname(sock.getpeername())

class Polling:
    """
        Select-based loop with timeouts and events.
    """

    def __init__ (self):
        self._poll = select.poll()
        self._poll_sockets = { }
    
    def poll_read (self, socket):
        """
            Register given socket for read() polling.
        """

        self._poll.register(socket, select.POLLIN)
        self._poll_sockets[socket.fileno()] = socket

    def poll (self, timeouts=None):
        """
            Run one polling cycle.

                timeouts        - sequence of (timer, time) values for timeouts
        """

        poll_timer = None
        poll_timeout = None
        
        if timeouts:
            # select shortest timeout
            for timer, timeout in timeouts:
                if not poll_timeout or timeout < poll_timeout:
                    poll_timer = timer
                    poll_timeout = timeout

        if poll_timeout:
            timeout = (poll_timeout - time.time()) * 1000

            if timeout < 0:
                log.warning("immediate timeout: %s@%f = %f", poll_timer, poll_timeout, timeout)
            else:
                log.debug("%f...", timeout)

            poll = self._poll.poll(timeout)
        else:
            log.debug("...")

            poll = self._poll.poll()


        if poll:
            for fd, event in poll:
                socket = self._poll_sockets[fd]
                
                # XXX: POLLIN vs POLLER?
                log.debug("%s: read..", socket)

                for recv in socket:
                    # read
                    yield socket, recv

        else:
            log.debug("%s: timeout", poll_timer)

            # timeout
            raise Timeout(poll_timer)

class Timeout(Exception):
    def __init__(self, value):
        self.timer = value

    def __str__(self):
        return repr(self.timer)
