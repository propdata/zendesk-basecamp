import ConfigParser
import sys
from os import path


class Config(object):
    def __init__(self):
        """
        Load config.ini
        """
        if not path.exists("zc.cfg"):
            print "Couldn't load zc.cfg - Please configure this first."
            sys.exit(1)

        config = ConfigParser.ConfigParser()
        config.readfp(open('zc.cfg'))

        self.config = config

    def zendesk(self):
        config_items = ["subdomain", "username", "password"]
        return dict(zip(config_items,
            map(lambda x: self.config.get("zendesk", x), config_items)))
