import argparse
import logging
import sys

def parser (parser) :
    args = parser.add_argument_group("Generic options")
    args.add_argument('-q', '--quiet',      dest='log_level', action='store_const', const=logging.ERROR,
            help="Less output")
    args.add_argument('-v', '--verbose',    dest='log_level', action='store_const', const=logging.INFO,
            help="More output")
    args.add_argument('-d', '--debug',      dest='log_debug', action='append',
            help="Debugging output for given module")

    parser.set_defaults(
            log_level       = logging.WARNING,
            log_debug       = [ ],
    )

def apply (args) :
    logging.basicConfig(
            format      = "{levelname:<8} {name:>30}:{funcName:<20} : {message}",
            style       = '{',
            level       = args.log_level,
    )

    for log in args.log_debug :
        logging.getLogger(log).setLevel(logging.DEBUG)

def main (main) :
    sys.exit(main(sys.argv[1:]))
