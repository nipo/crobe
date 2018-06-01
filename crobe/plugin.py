from . import config

for plugin in config.plugins_get():
    __import__(plugin)
