library ieee;
use ieee.std_logic_1164.all;

library work, nsl_io, nsl_hwdep;

entity boundary is
  port (
    spi_cs_n_o: inout std_logic;
    spi_mosi_o: out std_ulogic;
    spi_miso_i: in std_ulogic;
    spi_sck_o: out std_ulogic
  );
end boundary;

architecture arch of boundary is

  signal reset_n_s, clock_s : std_ulogic;
  signal spi_cs_n_s: nsl_io.io.opendrain;
  
begin

  internal_clock_gen: nsl_hwdep.clock.clock_internal
    port map(
      clock_o => clock_s
      );

  internal_reset_gen: nsl_hwdep.reset.reset_at_startup
    port map(
      clock_i => clock_s,
      reset_n_o => reset_n_s
      );
  
  main: work.func.jtag_spi
    generic map(
      clock_hz_c => 65e6
      )
    port map(
      reset_n_i => reset_n_s,
      clock_i => clock_s,
      spi_o.sck => spi_sck_o,
      spi_o.mosi => spi_mosi_o,
      spi_o.cs_n => spi_cs_n_s,
      spi_i.miso => spi_miso_i,
      led_o => open
      );
  
  cs_driver: nsl_io.io.opendrain_io_driver
    port map(
      io_io => spi_cs_n_o,
      v_i => spi_cs_n_s
      );

end arch;
