
import pubsub.jsonish
import pubsub.udp

import collections
import logging; log = logging.getLogger('pubsub.protocol')
import struct
import time
import zlib

class Error (Exception):
    pass

class Message (object):
    # flag bits
    NOACK       = 0x80
    COMPRESS    = 0x40
    
    # type enum
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
        return "({magic:x}){self.type_str}[{self.ackseq}:{self.seq}] {self.payload!r}".format(
                self    = self,
                magic   = self.magic or 0,
        )
    
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

        if compress:
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
        magic = msg.magic

        if not magic:
            magic = self.MAGIC

        if magic == self.MAGIC_V2:
            pack_type = (msg.type & 0x0F
                    |  (1 if msg.noack else 0) << 7
                    |  (1 if msg.compress else 0) << 6
            )
            unused = 0
            compress = msg.compress

        elif magic == self.MAGIC_V1:
            pack_type = (msg.type & 0x0F)
            unused = (0
                    |   (1 if not msg.noack else 0) << 15
            )
            compress = False
        else:
            raise Error("Invalid magic: {magic:x}".format(magic=magic))

        header = self.HEADER.pack(magic, pack_type, unused, msg.ackseq, msg.seq)

        # payload
        if msg.payload is None:
            payload = b''
        else:
            payload = pubsub.jsonish.build_bytes(msg.payload)

        if compress:
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

class Session:
    """
        A stateful interchange of Messages between two Transports.
    """

    def __init__ (self, transport, addr) :
        self.transport = transport
        self.addr = addr

        # { Message.TYPE: seq:int }
        self.sendseq = collections.defaultdict(int)
        self.recvseq = collections.defaultdict(int)

        # { Message.TYPE: time:float )
        self.sendtime = collections.defaultdict(lambda: None)
        
        # { Message.TYPE: ... }
        self.sendpayload = { }

        # detected client magic
        self.magic = None
    
    # Message.TYPE: def (self, payload) : response
    RECV = { }

    def recv (self, msg):
        """
            Process an incoming Message from the peer into a RECV handler.
        """
        
        log.debug("%s: %s", self, msg)

        # handle magic (Message syntax)
        if not self.magic:
            log.info("%s: magic %#04x", self, msg.magic)
            self.magic = msg.magic

        elif msg.magic != self.magic:
            log.warning("%s: magic %#04x <- %#04x", self, msg.magic, self.magic)
            self.magic = msg.magic


        # handle acks
        if msg.ackseq:
            # clear timeout for stateful requests
            sendseq = self.sendseq[msg.type]

            if msg.ackseq < sendseq:
                log.warning("%s: %s:%d: ignore late ack < %d", self, msg.type_str, msg.ackseq, sendseq)

            elif msg.ackseq > sendseq:
                log.warning("%s: %s:%d: ignore future ack > %d", self, msg.type_str, msg.ackseq, sendseq)

            else:
                sendtime = self.sendtime.pop(msg.type)
                del self.sendpayload[msg.type]

                log.debug("%s: %s:%d: ack @ %fs", self, msg.type_str, msg.ackseq, (time.time() - sendtime))
        
        elif self.sendtime.get(msg.type) and not self.sendseq.get(msg.type):
            # clear timeout for stateless queries
            sendtime = self.sendtime.pop(msg.type)
            del self.sendpayload[msg.type]
       

        # handle payloads
        recvseq = self.recvseq[msg.type]
        
        if not msg.seq and msg.ackseq:
            # payloadless ack
            pass

        elif msg.seq < recvseq:
            log.warning("%s: drop duplicate %s:%d < %d", self, msg.type_str, msg.seq, recvseq)

        elif msg.seq == recvseq and recvseq:
            log.warning("%s: dupack %s:%d", self, msg.type_str, msg.seq)

            self.transport(Message(msg.type, magic=msg.magic, ackseq=msg.seq), addr=self.addr)

        else:
            # process state update
            # XXX: seq might be zero?
            try :
                handler = self.RECV[msg.type]
            except KeyError :
                log.warning("%s: unknown message type: %s", self, msg)
                return
            
            try:
                # process request
                payload = handler(self, msg.payload)

            except Exception as ex:
                log.exception("%s: %s", self, msg)

            else:
                # processed state update
                self.recvseq[msg.type] = msg.seq

                ack = Message(msg.type,
                        magic   = msg.magic,
                        ackseq  = msg.seq,
                )
                
                if payload:
                    # ack + response
                    seq = self.sendseq[msg.type] + 1
        
                    log.info("%s: %s:%d:%s -> %d:%s", self, msg.type_str, msg.seq, msg.payload, seq, payload)
                    
                    ack.payload = payload
                    ack.seq = seq

                    self.sendseq[msg.type] = seq

                else:
                    # ack
                    log.info("%s: %s:%d:%s -> *", self, msg.type_str, msg.seq, msg.payload)

                self.transport(ack, addr=self.addr)

    def send (self, type, payload=None, magic=None, seq=True, **opts):
        """
            Build a Message and send it to the peer.

            Returns the sent Message.
        """
        
        # magic
        if magic is None:
            magic = self.magic
        
        if seq:
            # stateful query auto-sendseq
            seq = self.sendseq[type] + 1
        else:
            seq = 0
            

        msg = Message(type,
                magic   = magic,
                seq     = seq,
                payload = payload,
                **opts
        )

        log.info("%s: %s", self, msg)
        
        # send
        self.sendseq[type] = seq
        self.transport(msg, addr=self.addr)
        
        # update timeout for retry
        self.sendtime[type] = time.time()
        self.sendpayload[type] = payload

        return msg

    def retry (self, type):
        """
            Handle timeout for given message type by retransmitting the request.
        """
        
        msg = Message(type,
                magic   = self.magic,
                seq     = self.sendseq[type],
                payload = self.sendpayload[type],
        )
        
        log.warning("%s: %s", self, msg)

        # re-send
        self.transport(msg, addr=self.addr)
        self.sendtime[type] = time.time()

    def __str__ (self):
        if self.addr:
            return pubsub.udp.addrname(self.addr)
        else :
            return self.transport.peername()

