
import pubsub.jsonish
import pubsub.udp

import logging; log = logging.getLogger('pubsub.protocol')
import struct
import zlib

class Error (Exception):
    pass

class Message (object):
    NOACK       = 0x80
    COMPRESS    = 0x40

    SUBSCRIBE   = 0x00
    PUBLISH     = 0x01
    TEARDOWN    = 0x02

    TYPE_NAMES = {
        SUBSCRIBE:  'S',
        PUBLISH:    'P',
        TEARDOWN:   'T',
    }

    @classmethod
    def type_name (cls, type):
        return cls.TYPE_NAMES.get(type, '?')

    def __init__ (self, type, magic=0, noack=0, compress=0, ackseq=0, seq=0, payload=None, addr=None):
        """
            magic       - override default MAGIC for sent message
            noack       - indicate to receiver that we are not expecting any ackseq for our seq
            compress    - compress() payload before sending, indicate to receiver to decompress
            ...
        """

        self.magic = magic
        self.noack = noack
        self.compress = compress
        self.type = type
        self.ackseq = ackseq
        self.seq = seq
        self.payload = payload

        # meta
        self.addr = addr

    @property
    def type_str (self):
        return Message.type_name(self.type)

    def __str__ (self):
        return "{self.type_str}[{self.ackseq}:{self.seq}] {self.payload!r}".format(self=self)
    
class Transport (pubsub.udp.Socket):
    """
        Bidirectional UDP-based transport protocol.
    """
    
    MAGIC_V1 = 0x42
    MAGIC_V2 = 0x43

    MAGIC = MAGIC_V2
    HEADER = struct.Struct("! BBH I I")

    # support maximum-size UDP messages
    SIZE = 2**16

    def parse (self, buf, **opts):
        """
            Unpack str -> Message
        """

        # header
        magic, unpack_type, flags, ackseq, seq = self.HEADER.unpack(buf[:self.HEADER.size])

        if magic == self.MAGIC_V2:
            noack = bool(unpack_type & 0x80)
            compress = bool(unpack_type & 0x40)
            type = unpack_type & 0x0F

        elif magic == self.MAGIC_V1:
            type = unpack_type
            noack = not bool(flags & 0x8000) # XXX: not really
            compress = False

        else:
            raise Error("Invalid magic: {magic:x}".format(magic=magic))

        # payload
        payload = buf[self.HEADER.size:]

        if compress :
            # XXX: place some limits on maximum decompressed size
            payload = zlib.decompress(payload)

        payload = pubsub.jsonish.parse_bytes(payload)
 
        return Message(type,
                magic       = magic, 
                noack       = noack, 
                compress    = compress,
                ackseq      = ackseq,
                seq         = seq,
                payload     = payload, 
                **opts
        )

    def build (self, msg):
        """
            Pack Message -> str
        """

        # header
        magic = msg.magic if msg.magic else self.MAGIC
        pack_type = (msg.type & 0x0F
                |  (1 if msg.noack else 0) << 7
                |  (1 if msg.compress else 0) << 6
        )

        header = self.HEADER.pack(magic, pack_type, 0, msg.ackseq, msg.seq)

        # payload
        if msg.payload is None:
            payload = b''
        else:
            payload = pubsub.jsonish.build_bytes(msg.payload)

        if msg.compress :
            payload = zlib.compress(payload)
        
        return header + payload

    def __iter__ (self):
        """
            Yield parsed Messages received from clients.
        """

        for buf, addr in super(Transport, self).__iter__():
            try:
                msg = self.parse(buf, addr=addr)

            except Error as error:
                log.error("%s: invalid message: %s", addr, error)
                continue

            except pubsub.jsonish.ParseError as error:
                log.error("%s: invalid payload: %s", addr, error)
                continue

            log.debug("%s", msg)

            yield msg

    def __call__ (self, msg, addr=None):
        """
            Send a Message.
        """

        buf = self.build(msg)

        log.debug("%s: %s", addr, msg)

        super(Transport, self).__call__(buf, addr=addr)

