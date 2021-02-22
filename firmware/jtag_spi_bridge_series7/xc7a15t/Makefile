top = main.jtag_spi
target = jtag_spi
main-srcdir = $(SRC_DIR)/../src
target_part = xc7a15t
target_package = ftg256
target_speed = -1
hwdep = xilinx
tool = vivado

fw = ../../../crobe/component/xilinx/fw/artix7-15t_$(target).bit.gz

all: $(fw)

$(fw): $(target)-fast.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
