top = work.artix7.boundary
target = jtag_spi
work-srcdir = $(SRC_DIR)/../src
target_part = xc7a35t
target_package = ftg256
target_speed = -1
hwdep = xilinx
tool = vivado

fw = ../../../crobe/component/xilinx/fw/0x0362d093_jtag_spi.bit.gz

all: $(fw)

$(fw): $(target)-fast.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
