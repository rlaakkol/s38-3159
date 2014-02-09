import errno
import socket

import logging; log = logging.getLogger('pubsub.udp')

class Socket (object) :
    """
        UDP datagram-based socket interface, using python __call__ and __iter__ semantics.

        Passing nonblocking=True will result in __iter__ returning early once the socket would block.
        The object is select()'able, having a .fileno() method.
    """

    SIZE = 1500

    @classmethod
    def connect (cls, host, port, **opts) :
        try :
            ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
        except socket.gaierror as error :
            log.error("%s:%s: %s", port, host, error)
            raise

        for family, type, proto, canonname, sockaddr in ai :
            log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
            
            sock = socket.socket(family, type, proto)
            sock.connect(sockaddr)

            return cls(sock, **opts)

    @classmethod
    def listen (cls, port, host=None, **opts) :
        try :
            ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM, flags=socket.AI_PASSIVE)
        except socket.gaierror as error :
            log.error("%s:%s: %s", port, host, error)
            raise

        for family, type, proto, canonname, sockaddr in ai :
            log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
            
            sock = socket.socket(family, type, proto)
            sock.bind(sockaddr)

            return cls(sock, **opts)

    def __init__ (self, sock, nonblocking=None) :
        self.sock = sock

        if nonblocking is not None :
            self.sock.setblocking(not nonblocking)

    def fileno (self) :
        return self.sock.fileno()

    def __call__ (self, buf, addr=None) :
        """
            Send buf, addr from socket.
        """

        if addr :
            self.sock.sendto(buf, addr)
        else :
            self.sock.send(buf)

    def __iter__ (self) :
        """
            Yield buf, addr received from socket.
        """

        while True :
            try :
                # recv -> bytes, (sockaddr)
                buf, addr = self.sock.recvfrom(self.SIZE)

            except socket.error as error :
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK) :
                    # nonblocking
                    return
                else :
                    log.exception("recvfrom: %s", error)
                    raise
            
            yield buf, addr

    def __str__ (self) :
        try :
            sock_name = sockname(self.sock)

        except (socket.error, socket.gaierror) as ex :
            log.exception("%s", ex)
            sock_name = None

        try :
            peer_name = peername(self.sock)

        except socket.error as ex :
            if ex.errno == errno.ENOTCONN :
                # Transport endpoint is not connected
                pass
            else :
                log.exception("%s", ex)
                
            peer_name = None
            
        except socket.gaierror as ex :
            log.exception("%s", ex)
            peer_name = None

        return "{peername}{sockname}".format(
                peername    = ("<{peername}>".format(peername=peer_name) if peer_name else ''),
                sockname    = ("[{sockname}]".format(sockname=sock_name) if sock_name else ''),
        )

def sockname (sock) :
    """
        Return a human-readable representation of the socket local address.
    """

    addr = sock.getsockname()
    
    host, port = socket.getnameinfo(addr, socket.NI_DGRAM | socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)
    
    return "{host}:{port}".format(host=host, port=port)
 
def peername (sock) :
    """
        Return a human-readable representation of the socket remote address.
    """

    addr = sock.getpeername()
    
    host, port = socket.getnameinfo(addr, socket.NI_DGRAM | socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)

    return "{host}:{port}".format(host=host, port=port)
    
