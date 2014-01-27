
"""
    Publish-Subscribe client.
"""

import pubsub.jsonish

import logging; log = logging.getLogger('pubsub.client')
import socket

def udp_connect (host, port) :
    try :
        ai = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    except socket.gaierror as error :
        log.error("%s:%s: %s", port, host, error)
        raise

    for family, type, proto, canonname, sockaddr in ai :
        log.debug("family=%s type=%s sockaddr=%s", family, type, sockaddr)
        
        sock = socket.socket(family, type, proto)
        sock.connect(sockaddr)

        return sock

class Client :
    MSGSIZE = 1500

    def __init__ (self, server_ip, server_port) :
        self._server = udp_connect(server_ip, server_port)
        log.info("Connected to server on %s", self._server)

    def server (self, msg) :
        """
            Send a message to the server.
        """

        buf = pubsub.jsonish.build_bytes(msg)

        log.debug("%s", buf)

        self._server.send(buf)

    def subscribe (self, sensors) :
        """
            Send a subscribe message to the server.
        """

        msg = list(sensors)

        log.info("%s", msg)
        
        self.server(msg)

    def publish (self, msg) :
        """
            Process a publish from the server.
        """

        log.info("%s", msg)

    def main (self) :
        """
            Mainloop
        """

        while True :
            # recv -> bytes, (sockaddr)
            msg, addr = self._server.recvfrom(self.MSGSIZE)
            
            # parse
            try :
                msg = pubsub.jsonish.parse_bytes(msg)

            except pubsub.jsonish.ParseError as error :
                log.error("%s: invalid message: %s", addr, error)

            # process
            self.publish(msg)
