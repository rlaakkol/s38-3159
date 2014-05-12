"""
    Processing of data received from sensors.
"""

import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.sensors')

def parse_dev_id (dev_id):
    """
        Parse old-style dev_id -> dev_type, dev_index.

        Raises ValueError on invalid dev_id.
    """
    
    dev_type, dev_index = dev_id.split('_', 1)
    
    return dev_type, int(dev_index)

def parse_temp (data):
    """
        Parse temp sensor string.

        >>> parse_temp('41.6 C')
        41.6
    """

    temp = data.split(' ')

    return float(temp[0])

def parse_gps (data):
    """
        Parse GPS sensor string.

        >>> parse_gps('[60.182715, 24.79593]')
        [60.182715, 24.79593]
    """

    return pubsub.jsonish.parse(data)

PARSE_DATA = {
        'temp':     parse_temp,
        'gps':      parse_gps,
}

def parse (msg):
    """
        Parse a sensor update message into (type, id, { update }).
    """

    dev_type, dev_id = parse_dev_id(msg['dev_id'])

    parse_data = PARSE_DATA.get(dev_type)

    if parse_data:
        data = parse_data(msg['sensor_data'])
    else:
        data = msg['sensor_data']
    
    # parse metadata
    seq_no = msg['seq_no']
    ts = msg['ts']

    if isinstance(seq_no, str):
        seq_no = pubsub.jsonish.parse(seq_no)

    if isinstance(ts, str):
        ts = pubsub.jsonish.parse(ts)

    # build sensor update dict
    return dev_type, dev_id, {
            dev_type:       data,
            'seq_no':       seq_no,
            'ts':           ts,
    }

def parse_sensor_key (sensor_key):
    """
        Parse a new-style type:id key.
    """
    sensor_type, sensor_id = sensor_key.split(':')

    sensor_id = int(sensor_id)

    return sensor_type, sensor_id

class Transport (pubsub.udp.Socket):
    """
        Receiving sensor data updates from sensors.
    """
    
    # Maximum message length is 1667 bytes of sensor_data for camera, which can expand up to 4x = 6667 bytes,
    # plus other message overhead
    SIZE = 8000

    def __iter__ (self):
        """
            Yield dict messages received from sensors.
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
