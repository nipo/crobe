library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library nsl_coresight, nsl_i2c, nsl_bnoc,
  nsl_ftdi, nsl_clocking, nsl_io,
  nsl_ti, nsl_indication, nsl_jtag,
  nsl_spi;

entity main is
  generic(
    sys_clk_hz : natural
    );
  port(
    sys_clk: in std_ulogic;
    sys_resetn: in std_ulogic;

    user_led: out std_ulogic;
    button_pressed: in std_ulogic;

    dbg_tck_o: out std_ulogic;
    dbg_srst_o: out nsl_io.io.opendrain;
    dbg_srst_i: in std_ulogic;
    dbg_tms_o: out nsl_io.io.directed;
    dbg_tms_i: in std_ulogic;
    dbg_tdi_o: out nsl_io.io.directed;
    dbg_tdi_i: in std_ulogic;
    dbg_tdo_o: out nsl_io.io.directed;
    dbg_tdo_i: in std_ulogic;
    dbg_trst_o: out nsl_io.io.directed;
    dbg_trst_i: in std_ulogic;

    i2c_o : out nsl_i2c.i2c.i2c_o;
    i2c_i : in  nsl_i2c.i2c.i2c_i;

    ft245_i : in nsl_ftdi.ft245.ft245_sync_fifo_master_i;
    ft245_o : out nsl_ftdi.ft245.ft245_sync_fifo_master_o
    );
end main;

architecture arch of main is

  constant cs_reg_count : natural := 4;
  
  signal ft245_resetn_async, ft245_resetn : std_ulogic;
  signal ft245_clk : std_ulogic;
  signal user_resetn, user_resetn_async : std_ulogic;
  signal reset_sequence_received: std_ulogic;
  
  signal s_from_host, s_to_host : nsl_bnoc.framed.framed_bus_array(1 downto 0);
  signal s_from_host_sized, s_to_host_sized : nsl_bnoc.sized.sized_bus;

  type endpoint_comm is
  record
    routed_cmd, routed_rsp : nsl_bnoc.routed.routed_bus;
    framed_cmd, framed_rsp : nsl_bnoc.framed.framed_bus;
  end record;

  signal comm_swd, comm_i2c, comm_cs, comm_spi, comm_jtag, comm_cc : endpoint_comm;
  signal cc_o : nsl_ti.cc.cc_m_o;
  signal cc_i : nsl_ti.cc.cc_m_i;
  signal swd_o : nsl_coresight.swd.swd_master_o;
  signal swd_i : nsl_coresight.swd.swd_master_i;
  signal jtag_o : nsl_jtag.jtag.jtag_ate_o;
  signal jtag_i : nsl_jtag.jtag.jtag_ate_i;
  signal spi_o : nsl_spi.spi.spi_master_o;
  signal spi_i : nsl_spi.spi.spi_master_i;
  signal jtag_system_reset_n_o, swd_system_reset_n_o: nsl_io.io.opendrain;

  subtype mode_t is std_ulogic_vector(2 downto 0);
  signal mode: mode_t;
  constant mode_swd      : mode_t := "000";
  constant mode_jtag     : mode_t := "001";
  constant mode_cc       : mode_t := "010";
  constant mode_spi      : mode_t := "011";
  constant mode_spi_inv  : mode_t := "100";
  
  signal s_cs_config, s_cs_status: nsl_bnoc.control_status.control_status_reg_array(0 to cs_reg_count-1);

begin

  user_resetn_async <= sys_resetn and not reset_sequence_received and not button_pressed;
  ft245_resetn_async <= sys_resetn and not button_pressed;

  reset_sync_fifo: nsl_clocking.async.async_edge
    port map(
      clock_i => ft245_clk,
      data_i => ft245_resetn_async,
      data_o => ft245_resetn
      );

  reset_sync: nsl_clocking.async.async_edge
    port map(
      clock_i => sys_clk,
      data_i => user_resetn_async,
      data_o => user_resetn
      );
  
  ftdi_split: nsl_ftdi.ft245.ft245_sync_fifo_master
    generic map(
      burst_length => 64
      )
    port map(
      clock_o => ft245_clk,
      reset_n_i => ft245_resetn,

      bus_i => ft245_i,
      bus_o => ft245_o,

      in_ready_i => s_from_host_sized.ack.ready,
      in_valid_o => s_from_host_sized.req.valid,
      in_data_o => s_from_host_sized.req.data,

      out_ready_o => s_to_host_sized.ack.ready,
      out_valid_i => s_to_host_sized.req.valid,
      out_data_i => s_to_host_sized.req.data
      );

  to_framed: nsl_bnoc.sized.sized_to_framed
    port map(
      p_resetn => ft245_resetn,
      p_clk => ft245_clk,

      p_inval => reset_sequence_received,
      
      p_in_val => s_from_host_sized.req,
      p_in_ack => s_from_host_sized.ack,

      p_out_val => s_from_host(0).req,
      p_out_ack => s_from_host(0).ack
      );

  from_framed: nsl_bnoc.sized.sized_from_framed
    generic map(
      max_txn_length => 2048
      )
    port map(
      p_resetn => user_resetn,
      p_clk => ft245_clk,

      p_in_val => s_to_host(0).req,
      p_in_ack => s_to_host(0).ack,

      p_out_val => s_to_host_sized.req,
      p_out_ack => s_to_host_sized.ack
      );
  
  cmd_fifo: nsl_bnoc.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => user_resetn,
      p_clk(0) => ft245_clk,
      p_clk(1) => sys_clk,

      p_in_val => s_from_host(0).req,
      p_in_ack => s_from_host(0).ack,

      p_out_val => s_from_host(1).req,
      p_out_ack => s_from_host(1).ack
      );
  
  rsp_fifo: nsl_bnoc.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => user_resetn,
      p_clk(0) => sys_clk,
      p_clk(1) => ft245_clk,

      p_in_val => s_to_host(1).req,
      p_in_ack => s_to_host(1).ack,

      p_out_val => s_to_host(0).req,
      p_out_ack => s_to_host(0).ack
      );

  cmd_router: nsl_bnoc.routed.routed_router
    generic map(
      in_port_count => 1,
      out_port_count => 6,
      routing_table => (0, 1, 2, 3,
                        4, 5, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0)
      )
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,
      p_in_val(0) => s_from_host(1).req,
      p_in_ack(0) => s_from_host(1).ack,
      p_out_val(0) => comm_swd.routed_cmd.req,
      p_out_val(1) => comm_jtag.routed_cmd.req,
      p_out_val(2) => comm_i2c.routed_cmd.req,
      p_out_val(3) => comm_cs.routed_cmd.req,
      p_out_val(4) => comm_cc.routed_cmd.req,
      p_out_val(5) => comm_spi.routed_cmd.req,
      p_out_ack(0) => comm_swd.routed_cmd.ack,
      p_out_ack(1) => comm_jtag.routed_cmd.ack,
      p_out_ack(2) => comm_i2c.routed_cmd.ack,
      p_out_ack(3) => comm_cs.routed_cmd.ack,
      p_out_ack(4) => comm_cc.routed_cmd.ack,
      p_out_ack(5) => comm_spi.routed_cmd.ack
      );

  rsp_router: nsl_bnoc.routed.routed_router
    generic map(
      in_port_count => 6,
      out_port_count => 1,
      routing_table => (0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0)
      )
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,
      p_out_val(0) => s_to_host(1).req,
      p_out_ack(0) => s_to_host(1).ack,
      p_in_val(0) => comm_swd.routed_rsp.req,
      p_in_val(1) => comm_jtag.routed_rsp.req,
      p_in_val(2) => comm_i2c.routed_rsp.req,
      p_in_val(3) => comm_cs.routed_rsp.req,
      p_in_val(4) => comm_cc.routed_rsp.req,
      p_in_val(5) => comm_spi.routed_rsp.req,
      p_in_ack(0) => comm_swd.routed_rsp.ack,
      p_in_ack(1) => comm_jtag.routed_rsp.ack,
      p_in_ack(2) => comm_i2c.routed_rsp.ack,
      p_in_ack(3) => comm_cs.routed_rsp.ack,
      p_in_ack(4) => comm_cc.routed_rsp.ack,
      p_in_ack(5) => comm_spi.routed_rsp.ack
      );

  swd_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_swd.routed_cmd.req,
      p_cmd_in_ack  => comm_swd.routed_cmd.ack,
      p_rsp_out_val => comm_swd.routed_rsp.req,
      p_rsp_out_ack => comm_swd.routed_rsp.ack,

      p_cmd_out_val  => comm_swd.framed_cmd.req,
      p_cmd_out_ack  => comm_swd.framed_cmd.ack,
      p_rsp_in_val => comm_swd.framed_rsp.req,
      p_rsp_in_ack => comm_swd.framed_rsp.ack
      );

  jtag_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_jtag.routed_cmd.req,
      p_cmd_in_ack  => comm_jtag.routed_cmd.ack,
      p_rsp_out_val => comm_jtag.routed_rsp.req,
      p_rsp_out_ack => comm_jtag.routed_rsp.ack,

      p_cmd_out_val  => comm_jtag.framed_cmd.req,
      p_cmd_out_ack  => comm_jtag.framed_cmd.ack,
      p_rsp_in_val => comm_jtag.framed_rsp.req,
      p_rsp_in_ack => comm_jtag.framed_rsp.ack
      );

  i2c_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_i2c.routed_cmd.req,
      p_cmd_in_ack  => comm_i2c.routed_cmd.ack,
      p_rsp_out_val => comm_i2c.routed_rsp.req,
      p_rsp_out_ack => comm_i2c.routed_rsp.ack,

      p_cmd_out_val  => comm_i2c.framed_cmd.req,
      p_cmd_out_ack  => comm_i2c.framed_cmd.ack,
      p_rsp_in_val => comm_i2c.framed_rsp.req,
      p_rsp_in_ack => comm_i2c.framed_rsp.ack
      );

  cs_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_cs.routed_cmd.req,
      p_cmd_in_ack  => comm_cs.routed_cmd.ack,
      p_rsp_out_val => comm_cs.routed_rsp.req,
      p_rsp_out_ack => comm_cs.routed_rsp.ack,

      p_cmd_out_val  => comm_cs.framed_cmd.req,
      p_cmd_out_ack  => comm_cs.framed_cmd.ack,
      p_rsp_in_val => comm_cs.framed_rsp.req,
      p_rsp_in_ack => comm_cs.framed_rsp.ack
      );

  cc_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_cc.routed_cmd.req,
      p_cmd_in_ack  => comm_cc.routed_cmd.ack,
      p_rsp_out_val => comm_cc.routed_rsp.req,
      p_rsp_out_ack => comm_cc.routed_rsp.ack,

      p_cmd_out_val  => comm_cc.framed_cmd.req,
      p_cmd_out_ack  => comm_cc.framed_cmd.ack,
      p_rsp_in_val => comm_cc.framed_rsp.req,
      p_rsp_in_ack => comm_cc.framed_rsp.ack
      );

  spi_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => user_resetn,
      p_clk => sys_clk,

      p_cmd_in_val  => comm_spi.routed_cmd.req,
      p_cmd_in_ack  => comm_spi.routed_cmd.ack,
      p_rsp_out_val => comm_spi.routed_rsp.req,
      p_rsp_out_ack => comm_spi.routed_rsp.ack,

      p_cmd_out_val  => comm_spi.framed_cmd.req,
      p_cmd_out_ack  => comm_spi.framed_cmd.ack,
      p_rsp_in_val => comm_spi.framed_rsp.req,
      p_rsp_in_ack => comm_spi.framed_rsp.ack
      );
  
  dp: nsl_coresight.transactor.dp_framed_transactor
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,
      
      cmd_i => comm_swd.framed_cmd.req,
      cmd_o => comm_swd.framed_cmd.ack,

      rsp_o => comm_swd.framed_rsp.req,
      rsp_i => comm_swd.framed_rsp.ack,
      
      swd_o => swd_o,
      swd_i => swd_i,

      system_reset_n_o => swd_system_reset_n_o
      );

  i2c: nsl_i2c.transactor.transactor_framed_controller
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,

      cmd_i => comm_i2c.framed_cmd.req,
      cmd_o => comm_i2c.framed_cmd.ack,
      rsp_o => comm_i2c.framed_rsp.req,
      rsp_i => comm_i2c.framed_rsp.ack,

      i2c_o => i2c_o,
      i2c_i => i2c_i
      );

  ate: nsl_jtag.transactor.framed_ate
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,
      
      cmd_i => comm_jtag.framed_cmd.req,
      cmd_o => comm_jtag.framed_cmd.ack,
      rsp_o => comm_jtag.framed_rsp.req,
      rsp_i => comm_jtag.framed_rsp.ack,

      jtag_o => jtag_o,
      jtag_i => jtag_i,

      system_reset_n_o => jtag_system_reset_n_o
      );

  cs: nsl_bnoc.control_status.framed_control_status
    generic map(
      config_count_c => cs_reg_count,
      status_count_c => cs_reg_count
      )
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,
      
      cmd_i => comm_cs.framed_cmd.req,
      cmd_o => comm_cs.framed_cmd.ack,

      rsp_o => comm_cs.framed_rsp.req,
      rsp_i => comm_cs.framed_rsp.ack,

      config_o => s_cs_config,
      status_i => s_cs_status
      );

  cc: nsl_ti.cc.cc_framed_transactor
    generic map(
      divisor_shift => 2
      )
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,
      
      cmd_i => comm_cc.framed_cmd.req,
      cmd_o => comm_cc.framed_cmd.ack,
      rsp_o => comm_cc.framed_rsp.req,
      rsp_i => comm_cc.framed_rsp.ack,

      cc_i => cc_i,
      cc_o => cc_o
      );

  spi_trn: nsl_spi.transactor.spi_framed_transactor
    generic map(
      slave_count_c => 1
      )
    port map(
      clock_i  => sys_clk,
      reset_n_i => user_resetn,
      
      cmd_i => comm_spi.framed_cmd.req,
      cmd_o => comm_spi.framed_cmd.ack,
      rsp_o => comm_spi.framed_rsp.req,
      rsp_i => comm_spi.framed_rsp.ack,

      sck_o => spi_o.sck,
      cs_n_o(0) => spi_o.cs_n,
      mosi_o => spi_o.mosi,
      miso_i => spi_i.miso
      );

  mode <= s_cs_config(3)(mode'range);

  s_cs_status(0) <= std_ulogic_vector(to_unsigned(sys_clk_hz, s_cs_status(0)'length));
  s_cs_status(1)(0) <= not dbg_srst_i;
  s_cs_status(2)(0) <= dbg_trst_i;
  s_cs_status(3)(mode'range) <= mode;

  ios: process(mode, jtag_o, swd_o, cc_o, s_cs_config(1), spi_o,
               dbg_tdo_i, dbg_tdi_i, jtag_system_reset_n_o, swd_system_reset_n_o)
  begin
    dbg_tck_o <= '0';
    dbg_srst_o.drain_n <= not s_cs_config(1)(0);
    dbg_tms_o.output <= '0';
    dbg_tms_o.v <= '-';
    dbg_tdi_o.output <= '0';
    dbg_tdi_o.v <= '-';
    dbg_tdo_o.output <= '0';
    dbg_tdo_o.v <= '-';
    dbg_trst_o.output <= '0';
    dbg_trst_o.v <= '-';
    spi_i.miso <= '-';

    if mode = mode_swd then
      dbg_tms_o <= swd_o.dio;
      dbg_tck_o <= swd_o.clk;
      if swd_system_reset_n_o.drain_n = '0' then
        dbg_srst_o.drain_n <= '0';
      end if;
    elsif mode = mode_jtag then
      dbg_tck_o <= jtag_o.tck;
      dbg_tms_o.output <= '1';
      dbg_tms_o.v <= jtag_o.tms;
      dbg_trst_o.output <= jtag_o.trst;
      dbg_trst_o.v <= '1';
      dbg_tdi_o.output <= '1';
      dbg_tdi_o.v <= jtag_o.tdi;
      dbg_tdo_o.output <= '0';
      if jtag_system_reset_n_o.drain_n = '0' then
        dbg_srst_o.drain_n <= '0';
      end if;
    elsif mode = mode_cc then
      dbg_tck_o <= cc_o.dc;
      dbg_srst_o.drain_n <= not cc_o.reset_n;
      dbg_tms_o <= cc_o.dd;
    elsif mode = mode_spi then
      dbg_tck_o <= spi_o.sck;
      dbg_tms_o.v <= '0';
      dbg_tms_o.output <= not spi_o.cs_n.drain_n;
      dbg_tdi_o.output <= '1';
      dbg_tdi_o.v <= spi_o.mosi;
      spi_i.miso <= dbg_tdo_i;
    elsif mode = mode_spi_inv then
      dbg_tck_o <= spi_o.sck;
      dbg_tms_o.v <= '0';
      dbg_tms_o.output <= not spi_o.cs_n.drain_n;
      dbg_tdo_o.output <= '1';
      dbg_tdo_o.v <= spi_o.mosi;
      spi_i.miso <= dbg_tdi_i;
    end if;
  end process;
  
  cc_i.dd <= dbg_tms_i;
  swd_i.dio <= dbg_tms_i;
  jtag_i.tdo <= dbg_tdo_i;

  monitor: nsl_indication.activity.activity_monitor
    generic map(
      blink_cycles_c => sys_clk_hz / 8
      )
    port map(
      reset_n_i => sys_resetn,
      clock_i => sys_clk,
      togglable_i => ft245_resetn_async,
      activity_o => user_led
      );
  
end arch;
