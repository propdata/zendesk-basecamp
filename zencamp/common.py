import ConfigParser
import sys
from os import path


class AttributeInitType(type):
    def __call__(self, *args, **kwargs):
        obj = type.__call__(self, *args)

        for name, value in kwargs.items():
            setattr(obj, name, value)

        return obj


class BasecampConfig(object):
    __metaclass__ = AttributeInitType
    __slots__ = ['basecamp_id', 'username', 'password', 'project', 'todo_list',
            'auto_assign_to']
    _config_name = "basecamp"


class ZendeskConfig(object):
    __metaclass__ = AttributeInitType
    __slots__ = ['subdomain', 'username', 'password']
    _config_name = "zendesk"


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

    def _config_factory(self, klass):
        config_items = klass.__slots__
        return klass(**dict(zip(config_items,
            map(lambda x: self.config.get(klass._config_name, x),
                config_items))))

    def basecamp(self):
        return self._config_factory(BasecampConfig)

    def zendesk(self):
        return self._config_factory(ZendeskConfig)
