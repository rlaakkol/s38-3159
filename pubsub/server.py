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

        self.clients = set()

    def publish (self, msg) :
        """
            Send a publish message to all subscribed clients for this ServerSensor.
        """

        # publish
        log.info("%s: %s", self, msg)
        
        for client in self.clients | self.server.sensors_clients :
            client.send_publish(self, msg)

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

        self.sensors = set()
    
    def recv_subscribe (self, sensors) :
        """
            Process a subscription message from the client.
        """

        log.info("%s: %s", self, sensors)

        if sensors is True :
            # subscribe to all sensors
            for sensor in self.sensors :
                self.sensors.clients.remove(self)

            self.server.sensors_clients.add(self)

        else :
            # lookup ServerSensors
            sensors = set(self.server.lookup_sensors(sensors))

            # subscribe to specific sensors
            self.server.sensors_clients.discard(self)

            for sensor in self.sensors - sensors :
                sensor.clients.remove(self)

            for sensor in sensors - self.sensors :
                sensor.clients.add(self)

            self.sensors = sensors

    def send_publish (self, sensor, msg) :
        """
            Send a publish message for the given ServerSensor.
        """

        # publish
        log.info("%s: %s: %s", self, sensor, msg)

        publish = Message(Message.PUBLISH, payload=msg)
        
        self.send(publish)

    def send (self, msg) :
        self.transport(msg, addr=self.addr)

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
        
        # { ServerClient } of clients subscribed to all sensors
        self.sensors_clients = set()

    def lookup_sensors (self, sensors) :
        """
            Yield ServerSensors from list of sensor names.
        """

        for sensor_id in sensors :
            sensor = self.sensors.get(sensor_id)

            if sensor :
                yield sensor
            else :
                log.warning("unknown sensor: %s", sensor_id)

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
        
        sensor.publish(msg)
        
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
