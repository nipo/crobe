import sys

base, part, data_file = sys.argv[1:]

data = open(data_file, 'rb').read()

print('%s["%s"] = %r' % (base, part, data))
