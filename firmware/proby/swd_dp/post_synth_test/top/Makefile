vhdl-sources += topcell.vhd
vhdl-sources += swd_dp.vhd

$(top-srcdir)/swd_dp.vhd: $(SRC_DIR)/../ise-build/swd_dp_par.ncd
	$(SILENT)$(ISE_PREPARE) ; \
	netgen -sim -ofmt vhdl $< $@ -w
