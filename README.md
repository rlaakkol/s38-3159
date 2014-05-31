# S-38.3159 Protocol Design

## Source
    $ git clone git@github.com:rlaakkol/s38-3159.git

## Requirements

Package names from Debian APT:

* python3-numpy

### Sensors
    $ git submodule init
    $ git submodule update

## Usage
### Sensors
    $ cd SensorTrafficGenerator
    $ ./sensor.py temp 127.0.0.1 1336 1

### Server
    $ ./ps-server -v -p 1336 -s 1337

### Client
    $ ./ps-client -s localhost -p 1337

## Coding style

[PEP8](http://www.python.org/dev/peps/pep-0008/)

*   Indent 4-space

        :set tabstop=4 shiftwidth=4 expandtab

*   Use ' for machine-readable string literals.
    Use " for human-readable string literals.
