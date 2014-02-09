"""
    Publish-Subscribe server.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.sensors
import pubsub.udp

from pubsub.protocol import Message

import logging; log = logging.getLogger('pubsub.server')
import select

class ServerSensor :
    """
        Server per-sensor state
    """

    def __init__ (self, server, dev_id) :
        self.server = server
        self.dev_id = dev_id

    def update (self, update) :
        """
            Send a publish message to all subscribed clients for this ServerSensor.
        """

        # publish
        log.info("%s: %s", self, update)

        for client in self.server.clients.values() :
            client.sensor_update(self, update)
        
    def __str__ (self) :
        return self.dev_id

class ServerClient :
    """
        Server per-client state.
    """

    def __init__ (self, server, transport, addr) :
        self.server = server
        self.transport = transport
        self.addr = addr

        self.sensors = False

    def recv_subscribe (self, sensors) :
        """
            Process a subscription message from the client.
        """

        log.info("%s: %s", self, sensors)

        if sensors is True :
            # subscribe to all sensors
            self.sensors = True

        elif not sensors :
            # unsubscribe from all sensors
            self.sensors = False
        
        else :
            # subscribe to given sensors
            self.sensors = set(sensors)

    def sensor_update (self, sensor, update) :
        """
            Publish sensor update, if subscribed.
        """

        if self.sensors is True or str(sensor) in self.sensors :
            self.send_publish(update)

    def send_publish (self, update) :
        """
            Send a publish message for the given sensor update.
        """

        # publish
        log.info("%s: %s", self, update)

        self.send(Message.PUBLISH, update)

    def send (self, type, payload=None, **opts) :
        """
            Build a Message and send it to the client.
        """

        self.transport(Message(type, payload=payload, **opts), addr=self.addr)

    def __str__ (self) :
        return pubsub.udp.addrname(self.addr)

class Server :
    """
        Server state/logic implementation.
    """

    def __init__ (self, publish_port, subscribe_port) :
        self.sensor_port = pubsub.sensors.Transport.listen(publish_port, nonblocking=True)
        log.info("Listening for sensor publish messages on %s", self.sensor_port)

        self.client_port = pubsub.protocol.Transport.listen(subscribe_port, nonblocking=True)
        log.info("Listening for client subscribe messages on %s", self.client_port)

        # { dev_id: ServerSensor }
        self.sensors = { }
        
        # { addr: ServerClient }
        self.clients = { }
        
    def sensor (self, msg, addr) :
        """
            Process a publish message from a sensor.
        """

        sensor_id = msg['dev_id']

        # fix brain damage
        msg['seq_no'] = pubsub.jsonish.parse(msg['seq_no'])
        msg['ts'] = pubsub.jsonish.parse(msg['ts'])
        msg['data_size'] = pubsub.jsonish.parse(msg['data_size'])

        if msg['dev_id'].startswith('gps_') :
            msg['sensor_data'] = pubsub.jsonish.parse(msg['sensor_data'])

        # maintain sensor state
        if sensor_id in self.sensors :
            sensor = self.sensors[sensor_id]
        else :
            sensor = self.sensors[sensor_id] = ServerSensor(self, sensor_id)
            
            log.info("%s: new sensor", sensor)
        
        sensor.update(msg)
        
    def subscribe (self, msg, addr) :
        """
            Process a subscribe message from a client.
        """

        # maintain client state
        if addr in self.clients :
            client = self.clients[addr]
        else :
            client = self.clients[addr] = ServerClient(self, self.client_port, addr)
        
        # XXX: validate payload
        sensors = msg.payload
        
        try :
            client.recv_subscribe(sensors)
        except Exception as ex :
            # drop message...
            log.exception("ServerClient.subscribe failed: %s", ex)

    def __call__ (self) :
        """
            Mainloop
        """

        poll = select.poll()
        polling = { }

        for socket in [self.sensor_port, self.client_port] :
            poll.register(socket, select.POLLIN)
            polling[socket.fileno()] = socket

        while True :
            for fd, event in poll.poll() :
                sock = polling[fd]

                # process
                if sock == self.sensor_port:
                    for msg, addr in sock :
                        self.sensor(msg, addr)

                elif sock == self.client_port :
                    for msg, addr in sock :
                        if msg.type == Message.SUBSCRIBE :
                            self.subscribe(msg, addr)
                        else :
                            log.warning("Unhandled message type from client: %s", msg)

                else :
                    log.error("%s: unhandled message: %s", addr, msg)
