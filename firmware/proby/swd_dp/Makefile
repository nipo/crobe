top = work.topcell.swd_dp
target = swd_dp
hwdep=xilinx

all: ../../../crobe/adapter/proby/fw/$(target).bit.gz

../../../crobe/adapter/proby/fw/$(target).bit.gz: $(target)-compressed.bit
	gzip -c9 < $< > $@

include ../synthesis.mk
