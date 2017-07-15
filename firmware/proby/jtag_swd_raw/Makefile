libraries = work
work-srcdir = src
target = jtag_swd_raw
top = top

all: ../../../crobe/adapter/proby/fw/jtag_swd_raw.bit.gz

../../../crobe/adapter/proby/fw/jtag_swd_raw.bit.gz: jtag_swd_raw-compressed.bit
	gzip -c9 < $< > $@

include ../synthesis.mk
