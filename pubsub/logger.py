"""
    Logging class.
"""

import argparse
import os
import os.path

import logging; log = logging.getLogger('pubsub.logger')

LOGS = "logs"

def parser (parser, component, logs=LOGS) :
    args = parser.add_argument_group("Protocol logging options")
    args.add_argument('--log-dir', metavar='DIR', default="{logs}/{component}".format(logs=logs, component=component),
            help="Logging output directory")
    
    return args

def apply (args):
    return LoggerMain(args.log_dir)

class LoggerMain:
    """
        Logger multiplexer.
    """

    def __init__ (self, dir) :
        self.dir = dir
        self.loggers = { }

        if not os.path.exists(dir):
            log.warn("%s: mkdir", dir)
            os.mkdir(dir)
    
    def logger (self, logger):
        if logger not in self.loggers:
            self.loggers[logger] = Logger(os.path.join(self.dir, logger))

        return self.loggers[logger]

    def close (self) :
        for logger in self.loggers.values() :
            logger.close()

        self.loggers = { }

class Logger :
    """
        Individual logfile.
    """

    def __init__ (self, filename) :
        self.logfile = open(filename, 'w')

    def log (self, *fields) :
        """
            Logs a message consisting of tab-separated fields to the opened logfile.
        """

        self.logfile.write(str('\t'.join(str(field) for field in fields)) + '\n')

    def close (self) :
        """
            Closes the logfile.
        """

        self.logfile.close()
