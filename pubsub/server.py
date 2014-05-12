"""
    Publish-Subscribe server.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.sensors
import pubsub.udp

from pubsub.protocol import Message
import time

import logging; log = logging.getLogger('pubsub.server')

class ServerSensor:
    """
        Server per-sensor state
    """

    def __init__ (self, server, type, id, logger=None):
        """
            logger  - (optional) per-sensor log of received updates
        """

        self.server = server
        self.logger = logger
        
        # parsed sensor name
        self.type = type
        self.id = id

    def update (self, update, msg):
        """
            Process sensor update, updating all clients that may be subscribed.
                
                update:     { 'ts': float, 'seq_no': int, type: ... }
                msg:        legacy sensor dict
        """

        if self.logger:
            # received sensor data
            self.logger.log(time.time(), update)

        # update clients
        log.info("%s: %s", self, update)

        for client in self.server.sensor_clients(self):
            try:
                client.sensor_update(self, update, msg)
            except Exception as ex:
                # XXX: drop update...
                log.exception("ServerClient %s: sensor_update %s:%s", client, self, update)
        
    def __str__ (self):
        return '{self.type}:{self.id}'.format(self=self)

class ServerClient (pubsub.protocol.Session):
    """
        Server per-client state, using Session for protocol state.
    """

    def __init__ (self, server, transport, addr, logger=None):
        pubsub.protocol.Session.__init__(self, transport, addr)

        self.server = server
        self.logger = logger

        self.sensors = dict()
        self.sensors_all = False

    def recv_subscribe (self, sensors):
        """
            Process a subscription request from the client.
        """
        
        if sensors is True:
            # TODO: update on sensor change
            # subscribe to all sensors
            self.sensors = {sensor:True for sensor in self.server.sensors.keys()}
            self.sensors_all = True

        elif not sensors:
            # unsubscribe from all sensors
            self.sensors.clear()
            self.sensors_all = False

        # subscribe to given sensors
        elif isinstance(sensors, list):
            self.sensors = {sensor:True for sensor in sensors}
            self.sensors_all = False

        elif isinstance(sensors, dict):
            # TODO: parse sensor aggregation
            self.sensors = sensors
            self.sensors_all = False

        else:
            log.warning("%s: ignoring invalid subscribe-query payload (%s)" % (self, sensors))

    RECV = {
            Message.SUBSCRIBE:  recv_subscribe,
    }

    def sensor_update (self, sensor, update, legacy_msg):
        """
            Process sensor update.
        """

        if self.magic == 0x43:
            payload = { str(sensor): update }

        elif self.magic == 0x42:
            # pass through...
            payload = legacy_msg

        self.send_publish(payload)

    def sensor_add (self, sensor):
        """
            Process the addition of a new sensor.
        """
        # subscribed to all sensors
        # TODO: send subscribe update
        self.sensors[str(sensor)] = self.sensors_all

    def send_publish (self, update):
        """
            Send a publish message for the given sensor update.
        """

        self.send(Message.PUBLISH, update)
    
    def send (self, *args, **opts):
        """
            Send and log outgoing Messages.
        """

        msg = super(ServerClient, self).send(*args, **opts)

        if self.logger:
            self.logger.log(time.time(), str(msg))

class Server (pubsub.udp.Polling):
    """
        Server state/logic implementation.
    """

    def __init__ (self, publish_port, subscribe_port, sensors, loggers): 
        super(Server, self).__init__()

        # { sensor: ServerSensor }
        self.sensors = { }

        # { addr: ServerClient }
        self.clients = { }

        self.sensor_port = pubsub.sensors.Transport.listen(publish_port, nonblocking=True)
        log.info("Listening for sensor publish messages on %s", self.sensor_port)

        self.client_port = pubsub.protocol.Transport.listen(subscribe_port, nonblocking=True)
        log.info("Listening for client subscribe messages on %s", self.client_port)

        self.loggers = loggers

    def sensor (self, msg):
        """
            Process a publish message from a sensor.
        """
        
        # parse
        try:
            sensor_type, sensor_id, update = pubsub.sensors.parse(msg)
        except ValueError as error:
            log.warning("invalid sensor message: %s", msg)
            return

        sensor_key = '{type}:{id}'.format(type=sensor_type, id=sensor_id)

        # maintain sensor state
        if sensor_key in self.sensors:
            sensor = self.sensors[sensor_key]
        else:
            # new sensor
            sensor = self.sensors[sensor_key] = ServerSensor(self, sensor_type, sensor_id,
                    logger  = self.loggers.logger(sensor_key),
            )
            
            log.info("%s: add sensor", sensor)

            self.sensor_add(sensor)
       
        assert sensor_key == str(sensor)

        # publish update
        sensor.update(update, msg)
    
    def sensor_add (self, sensor):
        """
            Handle newly added ServerSensor.
        """
        
        # push new ServerSensor to ServerClients 
        for client in self.clients.values():
            client.sensor_add(sensor)

    def sensor_clients (self, sensor):
        """
            Yield all ServerClients subscribed to given ServerSensor.
        """

        for client in self.clients.values():
            if str(sensor) in client.sensors:
                yield client

    def client (self, msg, addr):
        """
            Process a message from a client.
        """
            
        log.debug("%s: %s", pubsub.udp.addrname(addr), msg)
        
        # stateful message?
        if msg.seq or msg.ackseq:
            # maintain client state
            if addr in self.clients:
                client = self.clients[addr]
            else:
                # create new stateful client Session
                client = self.clients[addr] = ServerClient(self, self.client_port, addr,
                        logger  = self.loggers.logger(pubsub.udp.addrname(addr)),
                )

            try:
                # process in client session
                client.recv(msg)
            except Exception as ex:
                # XXX: drop message...
                log.exception("ServerClient %s: %s", client, msg)

        elif msg.type == Message.SUBSCRIBE:
            try:
                # stateless query
                payload = self.client_subscribe_query(addr, msg.payload)
            
                # stateless response
                self.client_port.send(Message.SUBSCRIBE, payload, addr=addr)

            except Exception as ex:
                # XXX: drop message...
                log.exception("ServerClient %s: %s", pubsub.udp.addrname(addr), msg)

        else:
            log.warning("Unknown Message from unknown client %s: %s", addr, msg)

    def client_subscribe_query (self, addr, sensors=None):
        """
            Process a subscribe-query message from an unknown client
        """

        if sensors is not None:
            log.warning("%s: subscribe-query with payload: %s", pubsub.udp.addrname(addr), sensors)
        
        # response
        sensors = [str(sensor) for sensor in self.sensors.values()]

        log.info("%s: %s", pubsub.udp.addrname(addr), sensors)

        return sensors

    def __call__ (self):
        """
            Mainloop
        """
        
        # register UDP Sockets to read from
        self.poll_read(self.sensor_port)
        self.poll_read(self.client_port)

        while True:
            try:
                for socket, msg in self.poll():
                    # process
                    if socket == self.sensor_port:
                        # pubsub.sensors.Transport -> dict
                        self.sensor(msg)

                    elif socket == self.client_port:
                        # pubsub.protocol.Transport -> Message
                        self.client(msg, msg.addr)

                    else:
                        log.error("%s: message on unknown socket: %s", transport, msg)

            except pubsub.udp.Timeout as timeout:
                # TODO: handle sensor/client timeouts
                pass

