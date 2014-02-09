
import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.protocol')
import struct

class Error (Exception) :
    pass

class Message (object) :
    SUBSCRIBE   = 0x00
    PUBLISH     = 0x01
    TEARDOWN    = 0x02

    TYPE_NAMES = {
        SUBSCRIBE:  'S',
        PUBLISH:    'P',
        TEARDOWN:   'T',
    }

    def __init__ (self, type, flags=0, ack_seq=0, seq=0, payload=None) :
        self.type = type
        self.flags = flags
        self.ack_seq = ack_seq
        self.seq = seq
        self.payload = payload

    @property
    def type_str (self) :
        return self.TYPE_NAMES.get(self.type, '?')

    def __str__ (self) :
        return "{self.type_str}[{self.ack_seq}:{self.seq}] {self.payload!r}".format(self=self)
    
class Transport (pubsub.udp.Socket) :
    """
        Bidirectional UDP-based transport protocol.
    """
    
    MAGIC = 0x42
    HEADER = struct.Struct("! BBH I I")
    
    # support maximum-size UDP messages
    SIZE = 2**16

    def parse (self, buf) :
        # header
        magic, type, flags, ack_seq, seq = self.HEADER.unpack(buf[:self.HEADER.size])

        if magic != self.MAGIC :
            raise Error("Invalid magic: {magic:x}".format(magic=magic))

        # payload
        payload = pubsub.jsonish.parse_bytes(buf[self.HEADER.size:])
 
        return Message(type, flags, ack_seq, seq, payload)

    def build (self, msg) :
        # header
        header = self.HEADER.pack(self.MAGIC, msg.type, msg.flags, msg.ack_seq, msg.seq)

        # payload
        if msg.payload is None :
            payload = b''
        else :
            payload = pubsub.jsonish.build_bytes(msg.payload)
        
        return header + payload

    def __iter__ (self) :
        """
            Yield parsed Messages received from clients.
        """

        for buf, addr in super(Transport, self).__iter__() :
            try :
                msg = self.parse(buf)

            except Error as error :
                log.error("%s: invalid message: %s", addr, error)
                continue

            except pubsub.jsonish.ParseError as error :
                log.error("%s: invalid payload: %s", addr, error)
                continue

            log.debug("%s", msg)

            yield msg, addr

    def __call__ (self, msg, addr=None) :
        """
            Send a Message.
        """

        buf = self.build(msg)

        log.debug("%s: %s", addr, msg)

        super(Transport, self).__call__(buf, addr=addr)
