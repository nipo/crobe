set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]

set_property CFGBVS GND [current_design]
set_property CONFIG_VOLTAGE 1.8 [current_design]

set_property PACKAGE_PIN J13 [get_ports {spi_mosi_o}]
set_property PACKAGE_PIN J14 [get_ports {spi_miso_i}]
set_property PACKAGE_PIN L12 [get_ports {spi_cs_n_o}]
set_property PULLUP true [get_ports {spi_cs_n_o}]
set_property IOSTANDARD LVCMOS18 [get_ports {spi_*}]
set_property SLEW SLOW [get_ports {spi_*}]
set_property DRIVE 4 [get_ports {spi_*}]
