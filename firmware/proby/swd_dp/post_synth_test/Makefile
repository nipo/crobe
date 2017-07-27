top = tb.tb
target = swd_etm
tb-srcdir = $(SRC_DIR)/tb
top-srcdir = $(SRC_DIR)/top
hwdep=xilinx

tool = isim

$(target).vcd: rsp.txt cmd.txt

include ../../../../nsl/build/build.mk

rsp.txt cmd.txt: txn_gen
	./$< $@
