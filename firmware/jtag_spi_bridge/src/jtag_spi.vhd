library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library hwdep;
use hwdep.jtag.all;
use hwdep.clock.all;

library nsl;
use nsl.fifo.all;

library util;
use util.sync.all;

entity jtag_spi is
  port (
    p_flash_cs: out std_ulogic;
    p_flash_mosi: out std_ulogic;
    p_flash_miso: in std_ulogic;
    p_flash_sck: out std_ulogic
  );
end jtag_spi;

architecture arch of jtag_spi is

  signal s_clk_in, s_clk_out, s_resetn_in, s_resetn_out: std_ulogic;
  signal s_cmd_data, s_rsp_data: std_ulogic_vector(7 downto 0);
  signal s_cmd_ack, s_cmd_val, s_rsp_val, s_rsp_ack: std_ulogic;

  signal s_mosi_data, s_miso_data: std_ulogic_vector(7 downto 0);
  signal s_mosi_ack, s_mosi_val, s_miso_val, s_miso_ack: std_ulogic;

  signal s_clk_int, s_resetn_int: std_ulogic;

begin

  reset_int: util.sync.sync_rising_edge
    port map(
      p_in => s_resetn_in,
      p_out => s_resetn_int,
      p_clk => s_clk_int
      );
  
  clk: hwdep.clock.clock_internal
    port map(
      p_clk => s_clk_int
      );

  data_in: hwdep.jtag.jtag_inbound_fifo
    generic map(
      width => s_cmd_data'length,
      id => 1,
      sync_word_width => 16
      )
    port map(
      p_clk => s_clk_in,
      p_resetn => s_resetn_in,
      sync_word => X"AD5C",

      p_data => s_cmd_data,
      p_val => s_cmd_val
      );

  data_out: hwdep.jtag.jtag_outbound_fifo
    generic map(
      width => s_rsp_data'length,
      id => 2
      )
    port map(
      p_clk => s_clk_out,
      p_resetn => s_resetn_out,

      p_data => s_rsp_data,
      p_ack => s_rsp_ack
      );

  data_in_fifo: nsl.fifo.fifo_async
    generic map(
      data_width => s_cmd_data'length,
      depth => 2048
      )
    port map(
      p_resetn => s_resetn_in,

      p_in_clk => s_clk_in,
      p_in_data => s_cmd_data,
      p_in_write => s_cmd_val,
      p_in_full_n => s_cmd_ack,

      p_out_clk => s_clk_int,
      p_out_data => s_mosi_data,
      p_out_read => s_mosi_ack,
      p_out_empty_n => s_mosi_val
      );

  data_out_fifo: nsl.fifo.fifo_async
    generic map(
      data_width => s_rsp_data'length,
      depth => 2048
      )
    port map(
      p_resetn => s_resetn_out,
      
      p_in_clk => s_clk_int,
      p_in_data => s_miso_data,
      p_in_write => s_miso_val,
      p_in_full_n => s_miso_ack,

      p_out_clk => s_clk_out,
      p_out_data => s_rsp_data,
      p_out_read => s_rsp_ack,
      p_out_empty_n => s_rsp_val
      );

  spi: nsl.spi.spi_master
    generic map(
      slave_count => 1
      )
    port map(
      p_clk => s_clk_int,
      p_resetn => s_resetn_int,

      p_sck => p_flash_sck,
      p_mosi => p_flash_mosi,
      p_miso => p_flash_miso,
      p_csn(0) => p_flash_cs,

      p_cmd_val.data => s_mosi_data,
      p_cmd_val.val => s_mosi_val,
      p_cmd_val.more => '-',
      p_cmd_ack.ack => s_mosi_ack,

      p_rsp_val.data => s_miso_data,
      p_rsp_val.val => s_miso_val,
      p_rsp_val.more => open,
      p_rsp_ack.ack => s_miso_ack
      );

end arch;
