top = design.topcell.wrapper
target = jtag_swd_i2c
design-srcdir = $(SRC_DIR)/src
hwdep=xilinx
target_part = xc6slx9
target_package = tqg144
target_speed = -2
tool = ise

all: ../../../crobe/adapter/proby/fw/$(target).bit.gz

../../../crobe/adapter/proby/fw/$(target).bit.gz: $(target)-compressed.bit
	gzip -c9 < $< > $@

include ../../../nsl/build/build.mk
