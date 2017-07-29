top = tb.tb
target = swd_etm
tb-srcdir = $(SRC_DIR)/../src
top-srcdir = $(SRC_DIR)/../../src
hwdep=xilinx
tool = isim

include ../../../../../nsl/build/build.mk

$(target).vcd: rsp.txt cmd.txt

rsp.txt cmd.txt: ../txn_gen
	./$< $@
