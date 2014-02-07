"""
    Processing of data received from sensors.
"""

import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.sensors')

class Sensors (pubsub.udp.Socket) :
    """
        Receiving sensor data updates from sensors.
    """

    def __iter__ (self) :
        """
            Yield parsed messages received from sensors.
        """

        for buf, addr in super(Sensors, self).__iter__() :
            # parse
            try :
                msg = pubsub.jsonish.parse_bytes(buf)

            except pubsub.jsonish.ParseError as error :
                log.error("%s: invalid message: %s", addr, error)
                continue

            log.debug("%s: %s", addr, msg)

            yield msg, addr
