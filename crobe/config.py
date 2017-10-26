import configparser
import os
import os.path

_conf = configparser.ConfigParser()
_conf['cache'] = {'root': '~/.local/crobe/cache',
                   'bsdl': '%(root)s/bsdl'}

for filename in [os.path.expanduser('~/.config/crobe/crobe.conf'), 'crobe.conf']:
    _conf.read(filename)

def path_get(section, key):
    return os.path.expanduser(_conf[section][key])

def section_keys(section):
    return _conf.options(section)

