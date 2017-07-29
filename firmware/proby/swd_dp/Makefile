top = work.topcell.swd_dp
target = swd_dp
target_part = xc6slx9tqg144-2
constraints += $(SRC_DIR)/../pinout/ftdi_fifo.ucf
constraints += $(SRC_DIR)/../pinout/io0_dbg.ucf
constraints += $(SRC_DIR)/../pinout/user.ucf
constraints += $(SRC_DIR)/../pinout/clk.ucf
hwdep=xilinx
tool = ise

all: ../../../crobe/adapter/proby/fw/$(target).bit.gz

../../../crobe/adapter/proby/fw/$(target).bit.gz: $(target)-compressed.bit
	gzip -c9 < $< > $@

include ../../../nsl/build/build.mk
