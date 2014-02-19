"""
    Logging class.
"""

class Logger :
    def __init__(self, filename) :
        try :
            self.logfile = open(filename, 'w')
        except IOError :
            # TODO fix
            pass

    def log(self, message) :
        """
            Logs a message to the open logfile.
        """
        self.logfile.write(message)

    def close(self) :
        """
            Closes the logfile.
        """
        self.logfile.close()
