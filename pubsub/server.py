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

        self._clients = { }

    def publish (self, addr, msg) :
        """
            Process a publish message from a sensor.
        """

        # fix brain damage
        msg['seq_no'] = pubsub.jsonish.parse(msg['seq_no'])
        msg['ts'] = pubsub.jsonish.parse(msg['ts'])
        msg['data_size'] = pubsub.jsonish.parse(msg['data_size'])

        if msg['dev_id'].startswith('gps_') :
            msg['sensor_data'] = pubsub.jsonish.parse(msg['sensor_data'])
        
        log.info("%s: %s", addr, msg)

        for client in self._clients :
            self.client(client, msg)

    def subscribe (self, addr, msg) :
        """
            Process a subscribe message from a client.
        """

        log.info("%s: %s", addr, msg)

        self._clients[addr] = msg

    def client (self, addr, msg) :
        """
            Send client message.
        """
            
        log.info("%s: %s", addr, msg)
        
        buf = pubsub.jsonish.build_bytes(msg)

        self._subscribe.sendto(buf, addr)

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

                except pubsub.jsonish.ParseError as error :
                    log.error("%s: invalid message: %s", addr, error)
                    continue
                
                # process
                if sock == self._publish :
                    self.publish(addr, msg)

                elif sock == self._subscribe :
                    self.subscribe(addr, msg)

                else :
                    log.error("%s: unhandled message: %s", addr, msg)
