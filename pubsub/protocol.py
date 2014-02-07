
import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.protocol')

class Transport (pubsub.udp.Socket) :
    """
        Bidirectional UDP-based transport protocol.
    """

    def __iter__ (self) :
        """
            Yield parsed messages received from sensors.
        """

        for buf, addr in super(Transport, self).__iter__() :
            # parse
            try :
                msg = pubsub.jsonish.parse_bytes(buf)

            except pubsub.jsonish.ParseError as error :
                log.error("%s: invalid message: %s", addr, error)
                continue
            
            log.debug("%s: %s", addr, msg)

            yield msg, addr

    def __call__ (self, msg, addr=None) :
        """
            Build and send a message.
        """

        buf = pubsub.jsonish.build_bytes(msg)

        log.debug("%s: %s", addr, buf)

        super(Transport, self).__call__(buf, addr=addr)
