target = jtag_swapped
top = work.top
work-srcdir = $(SRC_DIR)/../src
target_part = xc6slx9tqg144-2
hwdep = xilinx
tool = ise

all: ../../../../crobe/adapter/proby/fw/jtag_swapped.bit.gz

../../../../crobe/adapter/proby/fw/jtag_swapped.bit.gz: jtag_swapped-compressed.bit
	gzip -c9 < $< > $@

include $(NSL)/build/build.mk
