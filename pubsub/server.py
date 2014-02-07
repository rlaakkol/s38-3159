"""
    Publish-Subscribe server.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.sensors

from pubsub.protocol import Message

import logging; log = logging.getLogger('pubsub.server')
import select

class Server :
    """
        Server state/logic implementation.
    """

    def __init__ (self, publish_port, subscribe_port) :
        self.sensors = pubsub.sensors.Sensors.listen(publish_port, nonblocking=True)
        log.info("Listening for sensor publish messages on %s", self.sensors)

        self.clients = pubsub.protocol.Transport.listen(subscribe_port, nonblocking=True)
        log.info("Listening for client subscribe messages on %s", self.clients)
        
        # socket
        self._clients = { }

    def publish (self, msg, addr) :
        """
            Process a publish message from a sensor.
        """

        sensor = msg['dev_id']

        # fix brain damage
        msg['seq_no'] = pubsub.jsonish.parse(msg['seq_no'])
        msg['ts'] = pubsub.jsonish.parse(msg['ts'])
        msg['data_size'] = pubsub.jsonish.parse(msg['data_size'])

        if msg['dev_id'].startswith('gps_') :
            msg['sensor_data'] = pubsub.jsonish.parse(msg['sensor_data'])
        
        log.info("%s: %s", addr, msg)

        publish = Message(Message.PUBLISH, payload=msg)

        for client_addr, sensors in self._clients.items() :
            # either empty list, or list containing sensor id
            if not sensors or sensor in sensors :
                self.clients(publish, client_addr)

    def subscribe (self, msg, addr) :
        """
            Process a subscribe message from a client.
        """
        
        # XXX: validate payload
        sensors = msg.payload

        log.info("%s: %s", addr, sensors)

        self._clients[addr] = sensors

    def __call__ (self) :
        """
            Mainloop
        """

        poll = select.poll()
        polling = { }

        for socket in [self.sensors, self.clients] :
            poll.register(socket, select.POLLIN)
            polling[socket.fileno()] = socket

        while True :
            for fd, event in poll.poll() :
                sock = polling[fd]

                # process
                if sock == self.sensors:
                    for msg, addr in self.sensors :
                        self.publish(msg, addr)

                elif sock == self.clients :
                    for msg, addr in self.clients :
                        if msg.type == Message.SUBSCRIBE :
                            self.subscribe(msg, addr)
                        else :
                            log.warning("Unhandled message type from client: %s", msg)

                else :
                    log.error("%s: unhandled message: %s", addr, msg)
