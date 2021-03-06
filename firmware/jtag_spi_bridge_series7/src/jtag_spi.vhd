library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library nsl_hwdep, nsl_bnoc, nsl_spi, nsl_jtag, nsl_indication, unisim, nsl_io;

entity jtag_spi is
  port (
    spi_cs_n_o: inout std_logic;
    spi_mosi_o: out std_ulogic;
    spi_miso_i: in std_ulogic
  );
end jtag_spi;

architecture arch of jtag_spi is

  type framed_io is
  record
    cmd, rsp : nsl_bnoc.framed.framed_bus;
  end record;
  
  type slave_conns is
  record
    post_fifo : framed_io;
    pre_fifo : framed_io;
  end record;

  signal comm_spi : slave_conns;
  signal spi_sck: std_ulogic;
  signal spi_cs_n: nsl_io.io.opendrain;

  signal reset_internal_n, reset_jtag_n, clock : std_ulogic;

  signal done_led_n : std_ulogic;
  
begin

  startupe2_inst : unisim.vcomponents.startupe2
    port map (
      cfgmclk => clock,
      eos => reset_internal_n,
      clk => '0',
      gsr => '0',
      gts => '0',
      keyclearb => '1',
      pack => '0',
      usrcclko => spi_sck,
      usrcclkts => '0', -- oe_n
      usrdoneo => '0',
      usrdonets => done_led_n -- oe_n
      );

  act: nsl_indication.activity.activity_monitor
    generic map(
      blink_cycles_c => 65000000 / 4,
      on_value_c => '0'
      )
    port map(
      reset_n_i => reset_internal_n,
      clock_i => clock,
      togglable_i => spi_cs_n.drain_n,
      activity_o => done_led_n
      );
  
  jtag_io: nsl_jtag.fifo_transport.jtag_fifo_transport_slave
    generic map(
      data_reg_no_c => 1,
      status_reg_no_c => 2,
      rx_fifo_depth_c => 2048,
      tx_fifo_depth_c => 2048,
      width_c => 9
      )
    port map(
      clock_i => clock,
      reset_n_i => reset_internal_n,
      reset_n_o => reset_jtag_n,

      tx_data_i(8) => comm_spi.pre_fifo.rsp.req.last,
      tx_data_i(7 downto 0) => comm_spi.pre_fifo.rsp.req.data,
      tx_valid_i => comm_spi.pre_fifo.rsp.req.valid,
      tx_ready_o => comm_spi.pre_fifo.rsp.ack.ready,

      rx_data_o(8) => comm_spi.pre_fifo.cmd.req.last,
      rx_data_o(7 downto 0) => comm_spi.pre_fifo.cmd.req.data,
      rx_valid_o => comm_spi.pre_fifo.cmd.req.valid,
      rx_ready_i => comm_spi.pre_fifo.cmd.ack.ready
      );

  inbound_fifo: nsl_bnoc.framed.framed_fifo
    generic map(
      depth => 4096,
      clk_count => 1
      )
    port map(
      p_resetn => reset_jtag_n,
      p_clk(0) => clock,

      p_in_val => comm_spi.pre_fifo.cmd.req,
      p_in_ack => comm_spi.pre_fifo.cmd.ack,

      p_out_val => comm_spi.post_fifo.cmd.req,
      p_out_ack => comm_spi.post_fifo.cmd.ack
      );

  outbound_fifo: nsl_bnoc.framed.framed_fifo
    generic map(
      depth => 4096,
      clk_count => 1
      )
    port map(
      p_resetn => reset_jtag_n,
      p_clk(0) => clock,

      p_out_val => comm_spi.pre_fifo.rsp.req,
      p_out_ack => comm_spi.pre_fifo.rsp.ack,

      p_in_val => comm_spi.post_fifo.rsp.req,
      p_in_ack => comm_spi.post_fifo.rsp.ack
      );

  spi_inst: nsl_spi.transactor.spi_framed_transactor
    generic map(
      slave_count_c => 1
      )
    port map(
      clock_i  => clock,
      reset_n_i => reset_jtag_n,
      
      sck_o => spi_sck,
      cs_n_o(0) => spi_cs_n,
      mosi_o => spi_mosi_o,
      miso_i => spi_miso_i,

      cmd_i => comm_spi.post_fifo.cmd.req,
      cmd_o => comm_spi.post_fifo.cmd.ack,
      rsp_o => comm_spi.post_fifo.rsp.req,
      rsp_i => comm_spi.post_fifo.rsp.ack
      );

  cs_driver: nsl_io.io.opendrain_io_driver
    port map(
      io_io => spi_cs_n_o,
      v_i => spi_cs_n
      );

end arch;
