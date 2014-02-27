"""
    Processing of data received from sensors.
"""

import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.sensors')

class Transport (pubsub.udp.Socket):
    """
        Receiving sensor data updates from sensors.
    """
    
    # Maximum message length is 1667 bytes of sensor_data for camera, which can expand up to 4x = 6667 bytes,
    # plus other message overhead
    SIZE = 8000

    def __iter__ (self):
        """
            Yield parsed messages received from sensors.
        """

        for buf, addr in super(Transport, self).__iter__():
            # parse
            try:
                msg = pubsub.jsonish.parse_bytes(buf)

            except pubsub.jsonish.ParseError as error:
                log.error("%s: invalid message: %s", addr, error)
                continue

            log.debug("%s: %s", addr, msg)
        
            # drop addr, as it has no meaning for sensors; every update is sent on a separate socket..
            yield msg
