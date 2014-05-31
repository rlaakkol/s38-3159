#!/usr/bin/env python3

from distutils.core import setup
from pubsub import __version__


setup(
    name            = 'pubsub',
    version         = __version__,
    description     = 'Publish-Subscribe protocol implementation',

    packages        = [
        'pubsub',
    ],
    scripts         = [
        'ps-client',
        'ps-server',
    ],

    install_requires    = [
        'numpy',
    ],
)
