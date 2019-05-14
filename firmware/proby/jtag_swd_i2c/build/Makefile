top = work.topcell.jtag_swd_i2c
target = jtag_swd_i2c
work-srcdir = $(SRC_DIR)/../src
constraints += $(SRC_DIR)/../../pinout/ftdi_fifo.ucf
constraints += $(SRC_DIR)/../../pinout/io0_dbg.ucf
constraints += $(SRC_DIR)/../../pinout/io1_i2c.ucf
constraints += $(SRC_DIR)/../../pinout/user.ucf
constraints += $(SRC_DIR)/../../pinout/clk.ucf
constraints += $(SRC_DIR)/../src/clocks.ucf
hwdep=xilinx
target_part = xc6slx9
target_package = tqg144
target_speed = -2
tool = ise

all: ../../../../crobe/adapter/proby/fw/$(target).bit.gz

../../../../crobe/adapter/proby/fw/$(target).bit.gz: $(target)-compressed.bit
	gzip -c9 < $< > $@

include ../../../../nsl/build/build.mk
