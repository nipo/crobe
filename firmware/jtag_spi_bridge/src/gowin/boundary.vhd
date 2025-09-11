library ieee;
use ieee.std_logic_1164.all;

library work, nsl_io, nsl_hwdep;

entity boundary is
  port (
    chip_tdi_i: in std_logic;
    chip_tck_i: in std_logic;
    chip_tms_i: in std_logic;
    chip_tdo_o: out std_logic;

    spi_sck_o: out std_ulogic;
    spi_cs_n_io: inout std_logic;
    spi_mosi_io: inout std_logic;
    spi_miso_io: inout std_logic;

    done_led_o : out std_ulogic
  );
end boundary;

architecture arch of boundary is

  signal reset_n_s, clock_s : std_ulogic;
  signal spi_cs_n_s: nsl_io.io.opendrain;
  signal spi_mosi_s: nsl_io.io.tristated;
  
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

  mosi: nsl_io.io.tristated_io_driver
    port map(
      io_io => spi_mosi_io,
      v_i => spi_mosi_s,
      v_o => open);

  main: work.func.jtag_spi
    generic map(
      clock_hz_c => 65e6
      )
    port map(
      reset_n_i => reset_n_s,
      clock_i => clock_s,

      chip_tdi_i => chip_tdi_i,
      chip_tck_i => chip_tck_i,
      chip_tms_i => chip_tms_i,
      chip_tdo_o => chip_tdo_o,

      spi_o.sck => spi_sck_o,
      spi_o.mosi => spi_mosi_s,
      spi_o.cs_n => spi_cs_n_s,
      spi_i.miso => spi_miso_io,

      led_o => done_led_o
      );
  
  cs_driver: nsl_io.io.opendrain_io_driver
    port map(
      io_io => spi_cs_n_io,
      v_i => spi_cs_n_s
      );

  spi_miso_io <= 'Z';

end arch;
