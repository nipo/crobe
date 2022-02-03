library ieee;
use ieee.std_logic_1164.all;

library work, unisim, nsl_io;

entity boundary is
  port (
    spi_cs_n_o: inout std_logic;
    spi_mosi_o: out std_ulogic;
    spi_miso_i: in std_ulogic
  );
end boundary;

architecture arch of boundary is

  signal reset_n_s, clock_s : std_ulogic;
  signal spi_sck_s: std_ulogic;
  signal spi_cs_n_s: nsl_io.io.opendrain;
  signal done_led_n_s, led_s : std_ulogic;
  
begin

  startupe2_inst : unisim.vcomponents.startupe2
    port map (
      cfgmclk => clock_s,
      eos => reset_n_s,
      clk => '0',
      gsr => '0',
      gts => '0',
      keyclearb => '1',
      pack => '0',
      usrcclko => spi_sck_s,
      usrcclkts => '0', -- oe_n
      usrdoneo => '0',
      usrdonets => done_led_n_s -- oe_n
      );

  done_led_n_s <= not led_s;
  
  main: work.func.jtag_spi
    generic map(
      clock_hz_c => 55e6
      )
    port map(
      reset_n_i => reset_n_s,
      clock_i => clock_s,
      spi_o.sck => spi_sck_s,
      spi_o.mosi => spi_mosi_o,
      spi_o.cs_n => spi_cs_n_s,
      spi_i.miso => spi_miso_i,
      led_o => led_s
      );
  
  cs_driver: nsl_io.io.opendrain_io_driver
    port map(
      io_io => spi_cs_n_o,
      v_i => spi_cs_n_s
      );

end arch;
