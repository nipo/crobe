top = work.jtag_spi
target = jtag_spi
work-srcdir = $(SRC_DIR)/../src
constraints += $(SRC_DIR)/pinout.ucf
hwdep = xilinx
target_part_name = xc6slx9
target_part_package = tqg144
target_part_speed = -2
target_part = $(target_part_name)$(target_part_package)$(target_part_speed)
tool = ise

fw = ../../../crobe/component/xilinx/fw/$(target_part_name)_$(target).bit.gz

all: $(fw)

$(fw): $(target)-compressed.bit
	gzip -c9 < $< > $@

include ../../../nsl/build/build.mk
