
"""
    Publish-Subscribe client.
"""

import pubsub.jsonish
import pubsub.protocol

import logging; log = logging.getLogger('pubsub.client')

class Client :
    def __init__ (self, server_ip, server_port) :
        self.server = pubsub.protocol.Transport.connect(server_ip, server_port)
        log.info("Connected to server on %s", self.server)

    def subscribe (self, sensors) :
        """
            Send a subscribe message to the server.
        """

        msg = list(sensors)

        log.info("%s", msg)
        
        self.server(msg)

    def publish (self, msg) :
        """
            Process a publish from the server.
        """

        log.info("%s", msg)

        return msg

    def __iter__ (self) :
        """
            Mainloop, yielding recv'd messages.
        """

        for msg, addr in self.server :
            # process
            yield self.publish(msg)
