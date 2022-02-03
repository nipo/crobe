library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library nsl_bnoc, nsl_spi, nsl_jtag, nsl_indication, nsl_io, nsl_clocking;

entity jtag_spi is
  generic(
    clock_hz_c : integer
    );
  port (
    clock_i : in std_ulogic;
    reset_n_i : in std_ulogic;

    chip_tdi_i: in std_ulogic := '0';
    chip_tck_i: in std_ulogic := '0';
    chip_tms_i: in std_ulogic := '0';
    chip_tdo_o: out std_logic;

    spi_o: out nsl_spi.spi.spi_master_o;
    spi_i: in nsl_spi.spi.spi_master_i;
    led_o : out std_ulogic
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

  signal reset_n_s, gen_reset_n_s : std_ulogic;
  
begin

  reset_sync: nsl_clocking.async.async_edge
    port map(
      clock_i => clock_i,
      data_i => reset_n_i,
      data_o => gen_reset_n_s
      );
  
  act: nsl_indication.activity.activity_monitor
    generic map(
      blink_cycles_c => clock_hz_c / 4,
      on_value_c => '1'
      )
    port map(
      reset_n_i => reset_n_s,
      clock_i => clock_i,
      togglable_i => comm_spi.pre_fifo.rsp.req.valid,
      activity_o => led_o
      );
  
  jtag_io: nsl_jtag.fifo_transport.jtag_fifo_transport_slave_tap
    generic map(
      status_enable_c => true,
      rx_fifo_depth_c => 256,
      tx_fifo_depth_c => 256,
      width_c => 9
      )
    port map(
      clock_i => clock_i,
      reset_n_i => gen_reset_n_s,
      reset_n_o => reset_n_s,

      chip_tdi_i => chip_tdi_i,
      chip_tck_i => chip_tck_i,
      chip_tms_i => chip_tms_i,
      chip_tdo_o => chip_tdo_o,

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
      depth => 256,
      clk_count => 1
      )
    port map(
      p_resetn => reset_n_s,
      p_clk(0) => clock_i,

      p_in_val => comm_spi.pre_fifo.cmd.req,
      p_in_ack => comm_spi.pre_fifo.cmd.ack,

      p_out_val => comm_spi.post_fifo.cmd.req,
      p_out_ack => comm_spi.post_fifo.cmd.ack
      );

  outbound_fifo: nsl_bnoc.framed.framed_fifo
    generic map(
      depth => 256,
      clk_count => 1
      )
    port map(
      p_resetn => reset_n_s,
      p_clk(0) => clock_i,

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
      clock_i  => clock_i,
      reset_n_i => reset_n_i,
      
      sck_o => spi_o.sck,
      cs_n_o(0) => spi_o.cs_n,
      mosi_o => spi_o.mosi,
      miso_i => spi_i.miso,

      cmd_i => comm_spi.post_fifo.cmd.req,
      cmd_o => comm_spi.post_fifo.cmd.ack,
      rsp_o => comm_spi.post_fifo.rsp.req,
      rsp_i => comm_spi.post_fifo.rsp.ack
      );

end arch;
