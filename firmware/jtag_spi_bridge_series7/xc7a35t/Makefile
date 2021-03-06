top = main.jtag_spi
target = jtag_spi
main-srcdir = $(SRC_DIR)/../src
target_part = xc7a35t
target_package = ftg256
target_speed = -1
hwdep = xilinx
tool = vivado

fw = ../../../crobe/component/xilinx/fw/xc7a35t_jtag_spi.bit.gz

all: $(fw)

$(fw): $(target)-fast.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
