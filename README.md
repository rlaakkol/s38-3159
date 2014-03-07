# S-38.3159 Protocol Design

## Build
    $ git clone git@github.com:rlaakkol/s38-3159.git

    $ git submodule init
    $ git submodule update

## Operate
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

*   Function `def` has extra whitespace before argument list

        def foo (bar) :
            return 42


