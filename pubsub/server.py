"""
    Publish-Subscribe server.
"""

import pubsub.jsonish

import logging; log = logging.getLogger('pubsub.server')
import select
import socket

def udp_listen (port, host=None) :
    try :
        ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM, flags=socket.AI_PASSIVE)
    except socket.gaierror as error :
        log.error("%s:%s: %s", port, host, error)
        raise

    for family, type, proto, canonname, sockaddr in ai :
        log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
        
        sock = socket.socket(family, type, proto)
        sock.bind(sockaddr)

        return sock

class Server :
    MSGSIZE = 1500

    def __init__ (self, publish_port, subscribe_port) :
        self._publish = udp_listen(publish_port)
        log.info("Listening for publish messages on %s", self._publish)

        self._subscribe = udp_listen(subscribe_port)
        log.info("Listening for subscribe messages on %s", self._subscribe)

    def publish (self, addr, msg) :
        """
            Process a publish message from a sensor.
        """

        log.info("%s: %s", addr, msg)

    def subscribe (self, addr, msg) :
        """
            Process a subscribe message from a client.
        """

        log.info("%s: %s", addr, msg)

    def main (self) :
        """
            Mainloop
        """

        poll = select.poll()
        polling = { }

        for socket in [self._publish, self._subscribe] :
            poll.register(socket, select.POLLIN)
            polling[socket.fileno()] = socket

        while True :
            for fd, event in poll.poll() :
                sock = polling[fd]

                # recv -> bytes, (sockaddr)
                msg, addr = sock.recvfrom(self.MSGSIZE)
                
                # parse
                try :
                    msg = pubsub.jsonish.parse_bytes(msg)

                except ValueError as error :
                    log.error("%s: invalid message: %s", addr, error)
                
                # process
                if sock == self._publish :
                    self.publish(addr, msg)

                elif sock == self._subscribe :
                    self.subscribe(addr, msg)

                else :
                    log.error("%s: unhandled message: %s", addr, msg)
