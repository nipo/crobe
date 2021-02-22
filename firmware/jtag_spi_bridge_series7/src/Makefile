vhdl-sources += jtag_spi.vhd
ifeq ($(tool),vivado)
implementation_constraint-sources += ../$(target_part)/pins.xdc
endif
deps += nsl_hwdep.clock
deps += nsl_hwdep.reset
deps += nsl_spi.transactor
deps += nsl_bnoc.framed
deps += nsl_jtag.fifo_transport
deps += nsl_indication.activity
