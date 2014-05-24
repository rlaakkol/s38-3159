
"""
    Publish-Subscribe client.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.sensors
import pubsub.udp

from pubsub.protocol import Message
from pubsub.logger import Logger

import time # XXX: logging
import logging; log = logging.getLogger('pubsub.client')
from os import getpid

class ClientSession (pubsub.protocol.Session):
    """
        Outbound state to server.
    """

    def __init__ (self, client, transport, addr, logger=None):
        pubsub.protocol.Session.__init__(self, transport, addr)

        self.client = client
        self.logger = logger

        # subscription state from server
        self.subscription = None
        
        # queued up publishes
        self.published = []

    def query_subscribe (self):
        """
            Send a stateless subscribe-query to the server.
        """

        log.info("")

        self.query(Message.SUBSCRIBE)

    def send_subscribe (self, sensors=None, **opts):
        """
            Send a subscribe query/request to the server.
        """

        log.info("%s", sensors)

        if isinstance(sensors, dict):
            # aggregation expression
            subscription = sensors
        else:
            if sensors is True:
                # subscribe-request: all
                subscription = True

            elif sensors:
                # subscribe-request: [sensor]
                subscription = list(sensors)
            
            elif not sensors:
                # subscribe-query
                subscription = None

            else:
                raise ValueError(sensors)
            
        self.send(Message.SUBSCRIBE, subscription, **opts)

    def recv_subscribe (self, subscription):
        """
            Process a subscribe-response/update from server.

            XXX: also handles subscribe-queryresponse, which has a different format!

            Maintains the subscription set in self.subscription.
        """
        
        log.info("%s", subscription)

        if self.subscription:
            # log changes
            for sensor in set(subscription) - set(self.subscription):
                log.info("add: %s", sensor)
            
            for sensor in set(self.subscription) - set(subscription):
                log.info("remove: %s", sensor)

        # update subscription state
        # XXX: this may also be a subscribe-queryresponse sensor list
        self.subscription = subscription

    def recv_publish (self, update):
        """
            Process a publish from the server.

            Queues up the (type, int(id), {update}) updates in self.published.
        """
        
        if self.magic == 0x42:
            # XXX: parse old-style update?
            sensor_type, sensor_id, update = pubsub.sensors.parse(update)
                
        elif self.magic == 0x43:
            # unpack new-style update
            # XXX: assumes it only contains one update
            for sensor_key, update in update.items():
                sensor_type, sensor_id = pubsub.sensors.parse_sensor_key(sensor_key)
        else:
            raise Exception("%s: unknown magic for publish syntax: %d" % (self, self.magic, ))
        
        log.info("%s:%d: %s", sensor_type, sensor_id, update)

        # enqueue
        self.published.append((sensor_type, sensor_id, update))


    RECV = {
            Message.SUBSCRIBE:  recv_subscribe,
            Message.PUBLISH:    recv_publish,
    }

class Client (pubsub.udp.Polling):

    def __init__ (self, server_ip, server_port, loggers):
        """
            server_ip       - str host
            server_port     - str service
            loggers         - pubsub.logger.LoggerMain
        """

        super(Client, self).__init__()

        self.server = pubsub.protocol.Transport.connect(server_ip, server_port,
                # required for timeouts
                nonblocking = True
        )
        log.info("Connected to server on %s", self.server)

        self.logger = loggers.logger(self.server.sockname())

        self.session = ClientSession(self, self.server, None,
                logger      = self.logger,
        )

    def recv (self, msg):
        """
            Handle received message.
        """

        # log all messages received
        self.logger.log(time.time(), str(msg))

        # stateful or stateless
        self.session.recv(msg)

    SEND_TIMEOUT = {
            Message.SUBSCRIBE:  10.0,
    }

    def poll_timeouts (self):
        """
            Collect timeouts for polling.
        """

        for type, sendtime in self.session.sendtime.items():
            if sendtime:
                timeout = sendtime + self.SEND_TIMEOUT[type]

                yield type, timeout, None

    def __iter__ (self):
        """
            Mainloop, yielding recv'd messages.
        """
        
        # register server Transport for reading
        self.poll_read(self.server)

        while True:
            try: 
                # read pubsub.udp.Sockets
                for socket, msg in self.poll(self.poll_timeouts()):
                    # XXX: verify sender addr
                    if socket != self.server:
                        log.error("poll on invalid socket: %s", socket)
                        continue
                    
                    # process message per client state
                    self.recv(msg)
                    
                    yield msg

            except pubsub.udp.Timeout as timeout:
                # timeout
                self.session.retry(timeout.timer)

    def query (self):
        """
            Send a query request, and return response list:

                [ 'type:id' ]
        """
        
        # using session for timeout/retry
        self.session.query_subscribe()

        for msg in self:
            # process messages until we get a subscription back
            if self.session.subscription is not None:
                return self.session.subscription

    def subscribe (self, sensors=True):
        """
            Setup a stateful subscription, and yield sensor publishes:

                (sensor_type, sensor_id, { update })

            Example:

                ('temp', 1, {'seq_no': 1068, 'ts': 1399929634.02, 'temp': 37.0})
        """

        self.session.send_subscribe(sensors)

        for msg in self:
            # consume queue
            for publish in self.session.published:
                yield publish

            self.session.published = []

    def __str__ (self):
        return str(self.server)
