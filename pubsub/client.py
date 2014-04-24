
"""
    Publish-Subscribe client.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.udp

from pubsub.protocol import Message
from pubsub.logger import Logger

import collections, time # XXX: protocol
import logging; log = logging.getLogger('pubsub.client')
from os import getpid

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

        self.sendseq = collections.defaultdict(int)
        self.sendtime = collections.defaultdict(lambda: None)
        
        self.logger = loggers.logger(self.server.sockname())

        # subscription state
        self.subscription = None

    def send (self, type, payload=None, seq=None, **opts):
        """
            Build a Message and send it to the server.
        """

        if seq is None and payload is not None:
            # stateful query auto-sendseq
            seq = self.sendseq[type] + 1
            self.sendseq[type] = seq

        elif not seq:
            # stateless query
            seq = 0

        msg = Message(type, payload=payload, seq=seq, **opts)

        log.debug("%s", msg)

        self.server(msg)

        self.sendtime[type] = time.time()

    SEND_TIMEOUT = {
            Message.SUBSCRIBE:  10.0,
    }

    def send_subscribe (self, sensors=None):
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
            
        self.send(Message.SUBSCRIBE, subscription)

        self.subscription = subscription

    def recv_subscribe (self, seq, sensors):
        """
            Process a subscribe-response/update from server.
        """
        
        log.info("%s", sensors)

        return sensors

    def recv_publish (self, seq, update):
        """
            Process a publish from the server.
        """

        update = { update['dev_id']: update['sensor_data'] }

        log.info("%s", update)

        return update
    
    RECV = {
            Message.SUBSCRIBE:  recv_subscribe,
            Message.PUBLISH:    recv_publish,
    }

    def recv (self, msg):
        """
            Handle received message.
        """

        log.debug("%s", msg)
        
        if msg.ackseq:
            sendseq = self.sendseq[msg.type]

            if msg.ackseq < sendseq:
                log.warning("%s:%d: late ack < %d", msg.type_str, msg.ackseq, sendseq)

            elif msg.ackseq > sendseq:
                log.warning("%s:%d: future ack > %d", msg.type_str, msg.ackseq, sendseq)

            else:
                sendtime = self.sendtime.pop(msg.type)

                log.debug("%s:%d: ack @ %fs", msg.type_str, msg.ackseq, (time.time() - sendtime))
        
        # XXX: handle as !ackseq && !seq?
        elif msg.type in self.sendseq and not self.sendseq[msg.type]:
            # clear sendtime for seqless queries
            sendtime = self.sendtime.pop(msg.type)
        
        if msg.seq or not msg.ackseq:
            # XXX: check seq
            if msg.type in self.RECV:
                ret = self.RECV[msg.type](self, msg.seq, msg.payload)
                
                log.debug("%s:%d:%s = %s", msg.type_str, msg.seq, msg.payload, ret)

                return ret

            else:
                log.warning("Received unknown message type from server: %s", msg)

    def timeout_subscribe (self, seq):
        """
            Retransmit subscribe.
        """

        log.warning("%d:%s", seq, self.subscription)
        
        self.send(Message.SUBSCRIBE, self.subscription, seq=seq)

    TIMEOUT = {
            Message.SUBSCRIBE:  timeout_subscribe,
    }

    def timeout (self, type):
        """
            Handle timeout on given sendtime.
        """

        seq = self.sendseq[type]

        if type in self.TIMEOUT:
            log.debug("%s:%d", Message.type_name(type), seq)

            self.TIMEOUT[type](self, seq)

        else:
            log.warning("%s:%d", Message.type_name(type), seq)

    def poll_timeouts (self):
        """
            Collect timeouts for polling.
        """

        for type, sendtime in self.sendtime.items():
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
                    if msg:
                        if type != self.server:
                            log.error("poll on invalid socket: %s", socket)
                            continue

                        # Transport -> Message
                        # XXX: check addr matches server addr
                        
                        out = self.recv(msg)

                        if out is not None:
                            yield msg.type, out

            except pubsub.udp.Timeout as timeout:
                    # timeout
                self.sendtime[timeout.timer] = None
                self.timeout(timeout.timer)

    def query (self):
        """
            Send a query request, and wait for response.
        """

        self.send_subscribe()

        for type, msg in self:
            if type == Message.SUBSCRIBE:
                return msg

            else:
                log.warning("unknown response to subscribe-query: %d:%s", type, msg)

    def subscribe (self, sensors=True):
        """
            Setup a subscription, and yield sensor publishes.
        """

        self.send_subscribe(sensors)

        for type, msg in self:
            if type == Message.PUBLISH:
                yield msg

            else:
                log.warning("unhandled response to subscribe-request: %d:%s", type, msg)

    def __str__ (self):
        return str(self.server)
