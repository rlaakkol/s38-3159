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

    def __init__ (self, server, dev_id, logger=None):
        """
            logger  - (optional) per-sensor log of received updates
        """
        self.server = server
        self.dev_id = dev_id
        self.logger = logger

    def recv (self, msg):
        """
            Process sensor update, updating all clients that may be subsribed.
        """

        if self.logger:
            # received sensor data
            self.logger.log(time.time(), msg)

        # reprocess
        update = {
                'dev_id':       msg['dev_id'],
                'sensor_data':  msg['sensor_data'],
                'seq_no':       pubsub.jsonish.parse(msg['seq_no']),
                'ts':           pubsub.jsonish.parse(msg['ts']),
                # data_size
        }

        # update clients
        log.info("%s: %s", self, update)

        for client in self.server.sensor_clients(self):
            try:
                client.sensor_update(self, update)
            except Exception as ex:
                # XXX: drop update...
                log.exception("ServerClient %s: sensor_update %s:%s", client, self, update)
        
    def __str__ (self):
        return self.dev_id

class ServerClient (pubsub.protocol.Session):
    """
        Server per-client state, using Session for protocol state.
    """

    def __init__ (self, server, transport, addr, logger=None):
        pubsub.protocol.Session.__init__(self, transport, addr)

        self.server = server

        self.sensors = set()
        self.logger = logger

    def recv_subscribe (self, sensors):
        """
            Process a subscription request from the client, or query if not seq.
        """
        
        if sensors is True:
            # subscribe to all sensors
            self.sensors = True

        elif not sensors:
            # unsubscribe from all sensors
            self.sensors = set()
        
        else:
            # subscribe to given sensors
            self.sensors = set(sensors)

    RECV = {
            Message.SUBSCRIBE:  recv_subscribe,
    }

    def sensor_update (self, sensor, update):
        """
            Process sensor update.
        """

        self.send_publish(update)

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

        # { dev_id: ServerSensor }
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

        sensor_id = msg['dev_id']

        # maintain sensor state
        if sensor_id in self.sensors:
            sensor = self.sensors[sensor_id]
        else:
            sensor = self.sensors[sensor_id] = ServerSensor(self, sensor_id,
                    logger  = self.loggers.logger(sensor_id),
            )
            
            log.info("%s: new sensor", sensor)
        
        sensor.recv(msg)
    
    def sensor_clients (self, sensor):
        """
            Yield all ServerClients subscribed to given sensor.
        """

        for client in self.clients.values():
            if client.sensors is True or str(sensor) in client.sensors:
                yield client

    def client (self, msg, addr):
        """
            Process a message from a client.
        """
            
        log.debug("%s: %s", pubsub.udp.addrname(addr), msg)

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
                client.recv(msg)
            except Exception as ex:
                # XXX: drop message...
                log.exception("ServerClient %s: %s", client, msg)

        elif msg.type == Message.SUBSCRIBE:
            # stateless query
            return self.client_subscribe_query(addr, msg.payload)

        else:
            log.warning("Message from unknown client %s: %s", addr, msg)
            return

    def client_subscribe_query (self, addr, sensors=None):
        """
            Process a subscribe-query message from an unknown client
        """

        if sensors is not None:
            log.warning("%s: subscribe-query with payload: %s", pubsub.udp.addrname(addr), sensors)


        sensors = [str(sensor) for sensor in self.sensors.values()]

        log.info("%s: %s", pubsub.udp.addrname(addr), sensors)

        self.client_port(Message(Message.SUBSCRIBE, payload=sensors), addr=addr)

    def __call__ (self):
        """
            Mainloop
        """

        self.poll_read(self.sensor_port)
        self.poll_read(self.client_port)

        while True:
            for socket, msg in self.poll():
                # process
                if socket == self.sensor_port:
                    # Sensors -> dict
                    self.sensor(msg)

                elif socket == self.client_port:
                    # Transport -> Message
                    self.client(msg, msg.addr)

                else:
                    log.error("%s: message on unknown socket: %s", socket, msg)

