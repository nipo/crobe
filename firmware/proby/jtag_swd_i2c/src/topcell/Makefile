vhdl-sources += topcell.pkg.vhd
vhdl-sources += main.vhd
vhdl-sources += clk_gen_spartan6.vhd
vhdl-sources += wrapper.vhd
constraint-sources += ../../../pinout/ftdi_fifo.ucf
constraint-sources += ../../../pinout/io0_dbg.ucf
constraint-sources += ../../../pinout/io1_i2c.ucf
constraint-sources += ../../../pinout/user.ucf
constraint-sources += ../../../pinout/clk.ucf
constraint-sources += clocks.ccf
constraint-sources += dbg_timing.ucf

deps += nsl_bnoc.framed
deps += nsl_bnoc.sized
deps += nsl_bnoc.routed
deps += nsl_bnoc.control_status

deps += nsl_ti.cc

deps += nsl_spi.transactor

deps += nsl_i2c.i2c
deps += nsl_i2c.transactor

deps += nsl_jtag.jtag
deps += nsl_jtag.transactor

deps += nsl_coresight.transactor
deps += nsl_hwdep.reset

deps += nsl_clocking.async
deps += nsl_indication.activity

deps += nsl_ftdi.ft245
deps += unisim.vcomponents
