
"""
    Publish-Subscribe client.
"""

import pubsub.jsonish
import pubsub.protocol
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

    def __init__ (self, client, transport, addr, logger=None) :
        pubsub.protocol.Session.__init__(self, transport, addr)

        self.client = client
        self.logger = logger

        # subscription state from server
        self.subscription = None
        
        # queued up publishes
        self.published = []

    def send_subscribe (self, sensors=None, **opts):
        """
            Send a subscribe query/request to the server.
        """

        log.info("%s", sensors)

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

    def recv_subscribe (self, sensors):
        """
            Process a subscribe-response/update from server.
        """
        
        log.info("%s", sensors)

        # orly
        self.subscription = sensors

    def recv_publish (self, update):
        """
            Process a publish from the server.
        """

        #update = { update['dev_id']: update['sensor_data'] }

        log.info("%s", update)

        self.published.append(update)
    
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

                yield type, timeout

    def __iter__ (self):
        """
            Mainloop, yielding recv'd messages.
        """
        
        self.poll_read(self.server)
        while True:
            try: 
                for type, msg in self.poll(self.poll_timeouts()):
                    # Transport -> Message

                    # XXX: verify sender addr
                    if type != self.server:
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
            Send a query request, and wait for response.
        """

        self.session.send_subscribe(seq=False)

        for msg in self:
            if self.session.subscription is not None :
                return self.session.subscription

    def subscribe (self, sensors=True):
        """
            Setup a subscription, and yield sensor publishes.
        """

        self.session.send_subscribe(sensors)

        for msg in self:
            for publish in self.session.published :
                yield publish

            self.session.published = []

    def __str__ (self):
        return str(self.server)
