target = jtag_swd_raw
top = work.top
work-srcdir = $(SRC_DIR)/../src
target_part = xc6slx9tqg144-2
constraints += $(SRC_DIR)/../../pinout/ftdi_jtag.ucf
constraints += $(SRC_DIR)/../../pinout/io0_dbg.ucf
constraints += $(SRC_DIR)/../../pinout/user.ucf
constraints += $(SRC_DIR)/../../pinout/clk.ucf
hwdep = xilinx
tool = ise

all: ../../../../crobe/adapter/proby/fw/jtag_swd_raw.bit.gz

../../../../crobe/adapter/proby/fw/jtag_swd_raw.bit.gz: jtag_swd_raw-compressed.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
