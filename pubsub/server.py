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

    def recv (self, msg) :
        """
            Process sensor update, updating all clients that may be subsribed.
        """

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

        for client in self.server.sensor_clients(self) :
            try :
                client.sensor_update(self, update)
            except Exception as ex :
                # XXX: drop update...
                log.exception("ServerClient %s: sensor_update %s:%s", client, self, update)
        
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

    def recv (self, msg) :
        """
            Process a message from the client.
        """

        if msg.type == Message.SUBSCRIBE :
            return self.recv_subscribe(msg.payload)

        else :
            log.warning("%s: Unhandled message type: %s", self, msg)

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
            Process sensor update.
        """

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

        # maintain sensor state
        if sensor_id in self.sensors :
            sensor = self.sensors[sensor_id]
        else :
            sensor = self.sensors[sensor_id] = ServerSensor(self, sensor_id)
            
            log.info("%s: new sensor", sensor)
        
        sensor.recv(msg)
    
    def sensor_clients (self, sensor) :
        """
            Yield all ServerClients subscribed to given sensor.
        """

        for client in self.clients.values() :
            if client.sensors is True or str(sensor) in client.sensors :
                yield client

    def client (self, msg, addr) :
        """
            Process a message from a client.
        """

        # maintain client state
        if addr in self.clients :
            client = self.clients[addr]
        else :
            client = self.clients[addr] = ServerClient(self, self.client_port, addr)
        
        try :
            client.recv(msg)
        except Exception as ex :
            # XXX: drop message...
            log.exception("ServerClient %s: %s", client, msg)

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
                        self.client(msg, addr)

                else :
                    log.error("%s: unhandled message: %s", addr, msg)
