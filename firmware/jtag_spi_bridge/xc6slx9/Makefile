top = work.spartan6.boundary
target = jtag_spi
work-srcdir = $(SRC_DIR)/../src
target_part = xc6slx9
target_package = tqg144
target_speed = -2
hwdep = xilinx
tool = ise

fw = ../../../crobe/component/xilinx/fw/0x04001093_jtag_spi.bit.gz

all: $(fw)

$(fw): $(target)-compressed.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
