import sys

name, data_file = sys.argv[1:]

data = open(data_file, 'rb').read()

print("%s = %r" % (name, data))
