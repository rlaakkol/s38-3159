"""
    Publish-Subscribe server.
"""

import pubsub.jsonish
import pubsub.protocol
import pubsub.sensors
import pubsub.udp

from pubsub.protocol import Message
import time
import numpy as np

from threading import Thread, Event

import logging; log = logging.getLogger('pubsub.server')

MIN_PUBACK_TIMEOUT = 3.0
MAX_PUBACK_TIMEOUT = 4.0
MAX_MISSED_ACKS = 2

class ServerSensor:
    """
        Server per-sensor state
    """

    def __init__ (self, server, type, id, logger=None):
        """
            logger  - (optional) per-sensor log of received updates
        """

        self.server = server
        self.logger = logger
        
        # parsed sensor name
        self.type = type
        self.id = id

        self.last_update = None

    def update (self, update, msg):
        """
            Process sensor update, updating all clients that may be subscribed.
                
                update:     { 'ts': float, 'seq_no': int, type: ... }
                msg:        legacy sensor dict
        """

        if self.logger:
            # received sensor data
            self.logger.log(time.time(), update)

        # update clients
        log.info("%s: %s", self, update)

        self.last_update = time.time()

        for client in self.server.sensor_clients(self):
            try:
                client.sensor_update(self, update, msg)
            except Exception as ex:
                # XXX: drop update...
                log.exception("ServerClient %s: sensor_update %s:%s", client, self, update)

    def has_timeout(self, timeout):
        """
            Checks whether a sensor has timeouted, that is, the last update is 
            older than 'timeout' seconds. Returns True on timeout, otherwise False.

                timeout:    the timeout value in seconds
        """

        if self.last_update:
            if time.time() - self.last_update > timeout:
                return True
        return False
        
    def __str__ (self):
        return '{self.type}:{self.id}'.format(self=self)

class ServerClient (pubsub.protocol.Session):
    """
        Server per-client state, using Session for protocol state.
    """

    def __init__ (self, server, transport, addr, logger=None):
        pubsub.protocol.Session.__init__(self, transport, addr)

        self.server = server
        self.logger = logger

        self.sensors = dict()
        self.sensors_all = False

        self.executor = None
        self.sensor_values = []

        self.last_ackreq = 0
        self.ack_pending = True
        self.missed_acks = 0
        self.timedout = False

    def sensors_state (self):
        """
            Return ('sensor:key', 1/0/-1) states for sensors.
        """

        for sensor_key, subscribed in self.sensors.items():
            if subscribed and sensor_key in self.server.sensors:
                # subscribed
                state = 1

            elif subscribed:
                # pending
                state = -1

            else:
                # not subscribed
                state = 0

            yield sensor_key, state

    def recv_subscribe (self, sensors):
        """
            Process a subscription request from the client.
        """
        
        if sensors is True:
            # subscribe to all sensors
            self.sensors = {sensor:True for sensor in self.server.sensors.keys()}
            self.sensors_all = True

        elif not sensors:
            # unsubscribe from all sensors
            self.sensors.clear()
            self.sensors_all = False

        # subscribe to given sensors
        elif isinstance(sensors, list):
            self.sensors = {sensor:True for sensor in sensors}
            self.sensors_all = False

        elif isinstance(sensors, dict):
            # sensor aggregation
            for key in sensors.keys():
                expr = sensors[key]
            
            def interval_handler (**opts):
                """
                    Performs aggregation specific action at the end of each 
                    aggregation interval.
                """
                
                server = opts['server']
                sensor = opts['sensor']
                expr = opts['expr']
                values = []
                key = 'temp' if sensor.find('temp') > -1 else 'gps'
                under = expr['under'] if 'under' in expr else None
                over = expr['over'] if 'over' in expr else None

                if expr['aggregate'] == 'last':
                    ok_values = self.check_under_over(under, over,
                        server.sensor_values, key)
                    if ok_values:
                        server.send_publish({sensor: ok_values})
                elif sensor.find('temp') > -1 or sensor.find('gps') > -1:
                    values = [value[key] for value in server.sensor_values]
                    if not values:
                        # no sensor updates received
                        return

                    if 'step' in expr:
                        # step provided
                        step_values = []
                        send_values = []
                        no_split = False
                        values_per_step = \
                            np.floor(expr['interval'] / expr['step'])
                        if len(values) > values_per_step:
                            splits = np.array_split(values, values_per_step)
                        else:
                            no_split = True

                        if no_split:
                            if expr['aggregate'] == 'max':
                                step_values = max(values)
                            elif expr['aggregate'] == 'min':
                                step_values = min(values)
                            elif expr['aggregate'] == 'avg':
                                step_values = np.mean(values, axis=0)
                            elif expr['aggregate'] == 'stddev':
                                step_values = np.std(values, axis=0)
                            send_values = {key: list(step_values), 'ts': time.time()}
                        else:
                            if expr['aggregate'] == 'max':
                                step_values = [max(list(split)) for split in splits]
                            elif expr['aggregate'] == 'min':
                                step_values = [min(list(split)) for split in splits]
                            elif expr['aggregate'] == 'avg':
                                step_values = [np.mean(split, axis=0)
                                    for split in splits]
                            elif expr['aggregate'] == 'stddev':
                                step_values = [np.std(split, axis=0)
                                    for split in splits]
                            send_values = [{key: value, 'ts': time.time()}
                                for value in step_values]
                        ok_values = self.check_under_over(under, over,
                            send_values, key)
                        if ok_values:
                            server.send_publish({sensor: ok_values})
                    else:
                        if expr['aggregate'] == 'max':
                            aggregate = max(values)
                        elif expr['aggregate'] == 'min':
                            aggregate = min(values)
                        elif expr['aggregate'] == 'avg':
                            aggregate = np.mean(values, axis=0)
                        elif expr['aggregate'] == 'stddev':
                            aggregate = np.std(values, axis=0)

                        if self.check_under_over(under, over, {key: aggregate},
                            key):
                            server.send_publish( {sensor: [ {key: aggregate,
                                'ts': time.time()} ]} )
                server.sensor_values = []

            if 'interval' in expr:
                self.executor = TimedExecutor(expr['interval'], interval_handler, 
                    server=self, sensor=key, expr=expr)
                self.executor.start()
            self.sensors = sensors
            self.sensors_all = False

        else:
            log.warning("%s: ignoring invalid subscribe-query payload (%s)" % (self, sensors))
        
        # response contains the real list of sensors
        return dict(self.sensors_state())


    def check_under_over (self, under, over, values, type):
        """
            Checks whether given value(s) (dict or list) fulfills the 'under'
            and 'over' constraints. Returns the conforming value(s) and an empty
            list otherwise.

            under  - under constraint
            over   - over constraint
            values - value(s) to check
            type   - type of sensor
        """

        passed_values = []
        # parse constraints
        try:
            if under:
                under = float(under)
            if over:
                over = float(over)
        except ValueError:
            # list because cast failed
            if under:
                under = [float(item) for item in under.split(',')]
            if over:
                over = [float(item) for item in over.split(',')]

        if isinstance(values, dict):
            # single dict
            if under and not over:
                # under
                if values[type] < under:
                    return values
            elif over and not under:
                # over
                if values[type] > over:
                    return values
            elif under and over:
                # both
                if values[type] < under and values[type] > over:
                    return values
        elif isinstance(values, list):
            # multiple dicts
            for val in values:
                if under and not over:
                    # under
                    if val[type] < under:
                        passed_values.append(val)
                elif over and not under:
                    # over
                    if val[type] > over:
                        passed_values.append(val)
                elif under and over:
                    # both
                    if val[type] < under and val[type] > over:
                        passed_values.append(val)
        if not under and not over:
            # pass-through if there are no constraints
            return values
        else:
            return passed_values

    def sensor_update (self, sensor, update, legacy_msg):
        """
            Process sensor update.
        """

        if self.magic == 0x43:
            payload = { str(sensor): update }

            if isinstance(self.sensors[str(sensor)], dict):
                # aggregation
                expr = self.sensors[str(sensor)]

                # under and over parameters
                sensor_type = 'temp' if str(sensor).find('temp') > -1 else 'gps'
                if ('under' in expr or 'over' in expr) and 'aggregate' not in expr:
                    if self.check_under_over(
                        expr['under'] if 'under' in expr else None,
                        expr['over'] if 'over' in expr else None,
                        update, 
                        sensor_type):
                        self.send_publish(payload)
                elif 'interval' in expr:
                    self.sensor_values.append(update)
            else:
                self.send_publish(payload)

        elif self.magic == 0x42:
            # pass through...
            payload = legacy_msg
            self.send_publish(payload)

    def sensor_add (self, sensor):
        """
            Process the addition of a new sensor.
        """

        subscribed = self.sensors.get(str(sensor))
        
        if not subscribed:
            # update subscription state to True if subscribing to all sensors
            self.sensors[str(sensor)] = self.sensors_all
        
        # send subscribe update
        self.send(Message.SUBSCRIBE, dict(self.sensors_state()))

    def send_publish (self, update, timeout=False):
        """
            Send a publish message for the given sensor update.
        """

        now = time.time()

        if timeout or now - self.last_ackreq > MIN_PUBACK_TIMEOUT:
            if self.ack_pending:
                if self.missed_acks > MAX_MISSED_ACKS:
                    self.timedout = True
                self.missed_acks += 1
            self.send(Message.PUBLISH, timeout=False, payload=update)
            self.last_ackreq = now
            self.ack_pending = True
        else:
            self.send(Message.PUBLISH, timeout=False, noack=True, payload=update)

    def handle_ack (self):
 #       log.info("Ack from client %s", self)
        self.ack_pending = False
        self.missed_acks = 0
    
    def send (self, *args, **opts):
        """
            Send and log outgoing Messages.
        """

        msg = super(ServerClient, self).send(*args, **opts)

        if self.logger:
            self.logger.log(time.time(), str(msg))

    RECV = {
            Message.SUBSCRIBE:  recv_subscribe,
            Message.PUBLISH:    handle_ack,
    }

    SEND_TIMEOUT = {
            Message.SUBSCRIBE: 10.0
    }


class Server (pubsub.udp.Polling):
    """
        Server state/logic implementation.
    """

    def __init__ (self, publish_port, subscribe_port, sensors, loggers): 
        super(Server, self).__init__()

        # { sensor: ServerSensor }
        self.sensors = { }

        # { addr: ServerClient }
        self.clients = { }

        self.sensor_port = pubsub.sensors.Transport.listen(publish_port, nonblocking=True)
        log.info("Listening for sensor publish messages on %s", self.sensor_port)

        self.client_port = pubsub.protocol.Transport.listen(subscribe_port, nonblocking=True)
        log.info("Listening for client subscribe messages on %s", self.client_port)

        self.loggers = loggers
        self.timeouts = []

    def sensor (self, msg):
        """
            Process a publish message from a sensor.
        """
        
        # parse
        try:
            sensor_type, sensor_id, update = pubsub.sensors.parse(msg)
        except ValueError as error:
            log.warning("invalid sensor message: %s", msg)
            return

        sensor_key = '{type}:{id}'.format(type=sensor_type, id=sensor_id)

        # maintain sensor state
        if sensor_key in self.sensors:
            sensor = self.sensors[sensor_key]
        else:
            # new sensor
            sensor = self.sensors[sensor_key] = ServerSensor(self, sensor_type, sensor_id,
                    logger  = self.loggers.logger(sensor_key),
            )
            
            log.info("%s: add sensor", sensor)

            self.sensor_add(sensor)
       
        assert sensor_key == str(sensor)

        # publish update
        sensor.update(update, msg)
    
    def sensor_add (self, sensor):
        """
            Handle newly added ServerSensor.
        """
        
        self.timeouts.append(str(sensor))
        # push new ServerSensor to ServerClients 
        for client in self.clients.values():
            client.sensor_add(sensor)

    def sensor_clients (self, sensor):
        """
            Yield all ServerClients subscribed to given ServerSensor.
        """

        for client in self.clients.values():
            if str(sensor) in client.sensors:
                yield client

    def client (self, msg, addr):
        """
            Process a message from a client.
        """
            
        log.debug("%s: %s", pubsub.udp.addrname(addr), msg)
        
        # stateful message?
        if msg.seq or msg.ackseq:
            # maintain client state
            if addr in self.clients:
                client = self.clients[addr]
            else:
                # create new stateful client Session
                client = self.clients[addr] = ServerClient(self, self.client_port, addr,
                        logger  = self.loggers.logger(pubsub.udp.addrname(addr)),
                )

            try:
                # process in client session
                client.recv(msg)
            except Exception as ex:
                # XXX: drop message...
                log.exception("ServerClient %s: %s", client, msg)

        elif msg.type == Message.SUBSCRIBE:
            try:
                # stateless query
                payload = self.client_subscribe_query(addr, msg.payload)
            
                # stateless response
                self.client_port.send(Message.SUBSCRIBE, payload, addr=addr)

            except Exception as ex:
                # XXX: drop message...
                log.exception("ServerClient %s: %s", pubsub.udp.addrname(addr), msg)

        else:
            log.warning("Unknown Message from unknown client %s: %s", addr, msg)

    def client_subscribe_query (self, addr, sensors=None):
        """
            Process a subscribe-query message from an unknown client
        """

        if sensors is not None:
            log.warning("%s: subscribe-query with payload: %s", pubsub.udp.addrname(addr), sensors)
        
        # response
        sensors = [str(sensor) for sensor in self.sensors.values()]

        log.info("%s: %s", pubsub.udp.addrname(addr), sensors)

        return sensors

    def poll_timeouts (self):
        """
            Collect timeouts for polling.
        """
        for sensor in self.timeouts:
            yield sensor, time.time() + 60, None
        for addr, client in self.clients.items():
            for type, sendtime in client.sendtime.items():
                if sendtime:
                    timeout = sendtime + client.SEND_TIMEOUT[type]

                    yield type, timeout, None
            if not client.ack_pending:
                yield Message.PUBLISH, client.last_ackreq + MAX_PUBACK_TIMEOUT, client


    def __call__ (self):
        """
            Main loop
        """
        
        # register UDP Sockets to read from
        self.poll_read(self.sensor_port)
        self.poll_read(self.client_port)

        client = None
        remove = False

        while True:
            try:
                # Look foor clients that have timed out
                for key, client in self.clients.items():
                    if client.timedout:
                        remove = True
                        break
                if remove:
                    # Remove first timed out
                    log.warning("%s: removed client after timeout", client)
                    del self.clients[key]
                    remove = False

                for socket, msg in self.poll(self.poll_timeouts()):
                    # process
                    if socket == self.sensor_port:
                        # pubsub.sensors.Transport -> dict
                        self.sensor(msg)

                    elif socket == self.client_port:
                        # pubsub.protocol.Transport -> Message
                        self.client(msg, msg.addr)

                    else:
                        log.error("%s: message on unknown socket: %s", transport, msg)

            except pubsub.udp.Timeout as timeout:
                log.info("Publish timed out %s: %s", timeout.timer, timeout.session)
                # TODO: handle sensor/client timeouts
                if timeout.timer == Message.PUBLISH:

                    timeout.session.send_publish(None, timeout=True)
                else:
                    # handle sensor timeouts
                    timeout_sensors = []
                    for sensor in self.sensors:
                        if str(sensor) == str(timeout).strip("'"):
                            timeout_sensors.append(sensor)
                    # remove timeouted sensors
                    for sensor in timeout_sensors:
                        log.warning("%s: removed sensor after timeout" % sensor)
                        del self.timeouts[self.timeouts.index(str(sensor))]
                        del self.sensors[sensor]

class TimedExecutor(Thread):
    """
        Calls a function repeatedly after a specific time.
        Inspired by: https://stackoverflow.com/questions/12435211/python-threading-timer-repeat-function-every-n-seconds
    """
    def __init__(self, wait_time, func, **kwargs):
        """
            wait_time:  how many seconds to wait between function calls
            server:     the server instance
            func:       the function to be called
            kwargs:     keyword arguments to the function
        """

        Thread.__init__(self)
        self.stopped = Event()
        self.wait_time = wait_time
        self.func = func
        self.kwargs = kwargs

    def run(self):
        """
            Function executed by the thread.
        """
        while not self.stopped.wait(self.wait_time):
            self.func(**self.kwargs)
