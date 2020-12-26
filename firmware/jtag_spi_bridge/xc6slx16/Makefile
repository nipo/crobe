top = main.jtag_spi
target = jtag_spi
main-srcdir = $(SRC_DIR)/../src
target_part = xc6slx16
target_package = csg225
target_speed = -2
hwdep = xilinx
tool = ise

fw = ../../../crobe/component/xilinx/fw/spartan6-lx16_$(target).bit.gz

all: $(fw)

$(fw): $(target)-compressed.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
