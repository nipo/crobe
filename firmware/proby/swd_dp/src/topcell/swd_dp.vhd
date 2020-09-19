library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library nsl_coresight, nsl_bnoc, main, nsl, nsl_clocking, signalling, util;

entity swd_dp is
  port (
    clk: in std_ulogic;

    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    io_en: out std_ulogic;
    jtag_en: out std_ulogic;

    dbg_spare: in std_logic;
    dbg_srst: inout std_logic;
    dbg_rtck: in std_logic;
    dbg_tck: out std_logic;
    dbg_tms: inout std_logic;
    dbg_tdi: out std_logic;
    dbg_tdo: in std_logic;
    dbg_trst: inout std_logic;

    fifo_data: inout std_logic_vector(7 downto 0);
    fifo_rxfn: in std_ulogic;
    fifo_txen: in std_ulogic;
    fifo_rdn: out std_ulogic;
    fifo_wrn: out std_ulogic;
    fifo_oen: out std_ulogic;
    fifo_clk: in std_ulogic
  );
end swd_dp;

architecture arch of swd_dp is

  signal s_fifo_resetn, s_sys_resetn : std_ulogic;
  signal s_fifo_clk : std_ulogic;
  signal s_sys_clk : std_ulogic;
  signal s_sys_resetn_soft, s_resetn_soft_async, s_invalid_input: std_ulogic;
  
  signal s_from_host, s_to_host : nsl_bnoc.framed.framed_bus_array(1 downto 0);
  signal s_from_host_sized, s_to_host_sized : nsl_bnoc.sized.sized_bus;
  signal s_swd_cmd, s_swd_rsp : nsl_bnoc.framed.framed_bus;
  signal s_routed_swd_cmd, s_routed_swd_rsp : nsl_bnoc.routed.routed_bus;
  signal s_routed_cs_cmd, s_routed_cs_rsp : nsl_bnoc.routed.routed_bus;
  signal s_cs_cmd, s_cs_rsp : nsl_bnoc.framed.framed_bus;

  signal swd_o : nsl_coresight.swd.swd_master_o;
  
  signal s_srst, s_trst : std_ulogic;
  
  signal s_io_config: std_ulogic_vector(1 downto 0);
  signal s_config_data: nsl.cs.cs_reg;
  signal s_config_write: std_ulogic_vector(2 downto 0);
  signal s_status: nsl.cs.cs_reg_array(2 downto 0);
  
  constant sys_clk_hz : natural := 900000000 / 9;
  
begin

  s_resetn_soft_async <= s_sys_resetn and not s_invalid_input and user_btn;

  sys_clk_gen: main.topcell.clk_gen
    generic map(
      sys_clk_hz => sys_clk_hz
      )
    port map(
      p_clk_12 => clk,
      p_resetn => user_btn,
      p_sys_clk => s_sys_clk,
      p_sys_clk_ready => s_sys_resetn
      );

  reset_sync_fifo: nsl_clocking.async.async_edge
    port map(
      clock_i => s_fifo_clk,
      data_i => s_sys_resetn,
      data_o => s_fifo_resetn
      );

  reset_sync: nsl_clocking.async.async_edge
    port map(
      clock_i => s_sys_clk,
      data_i => s_resetn_soft_async,
      data_o => s_sys_resetn_soft
      );
  
  ftdi_split: nsl.ftdi.ft245_sync_fifo_master
    generic map(
      burst_length => 64
      )
    port map(
      p_clk => s_fifo_clk,
      p_resetn => s_fifo_resetn,

      p_ftdi_clk => fifo_clk,
      p_ftdi_data => fifo_data,
      p_ftdi_rxfn => fifo_rxfn,
      p_ftdi_txen => fifo_txen,
      p_ftdi_rdn => fifo_rdn,
      p_ftdi_wrn => fifo_wrn,
      p_ftdi_oen => fifo_oen,

      p_in_ready => s_from_host_sized.ack.ready,
      p_in_valid => s_from_host_sized.req.valid,
      p_in_data => s_from_host_sized.req.data,

      p_out_ready => s_to_host_sized.ack.ready,
      p_out_valid => s_to_host_sized.req.valid,
      p_out_data => s_to_host_sized.req.data
      );

  to_framed: nsl_bnoc.sized.sized_to_framed
    port map(
      p_resetn => s_fifo_resetn,
      p_clk => s_fifo_clk,

      p_inval => s_invalid_input,
      
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
      p_resetn => s_sys_resetn_soft,
      p_clk => s_fifo_clk,

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
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => s_fifo_clk,
      p_clk(1) => s_sys_clk,

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
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => s_sys_clk, -- input is port 0
      p_clk(1) => s_fifo_clk,

      p_in_val => s_to_host(1).req,
      p_in_ack => s_to_host(1).ack,

      p_out_val => s_to_host(0).req,
      p_out_ack => s_to_host(0).ack
      );

  dp: nsl_coresight.transactor.dp_framed_transactor
    port map(
      clock_i  => s_sys_clk,
      reset_n_i => s_sys_resetn_soft,
      
      cmd_i => s_swd_cmd.req,
      cmd_o => s_swd_cmd.ack,

      rsp_o => s_swd_rsp.req,
      rsp_i => s_swd_rsp.ack,
      
      swd_o => swd_o,
      swd_i.dio => dbg_tms
      );

  cs: nsl.cs.cs_framed_reg
    generic map(
      config_count => s_config_write'length,
      status_count => s_status'length
      )
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,
      
      p_cmd_val => s_cs_cmd.req,
      p_cmd_ack => s_cs_cmd.ack,

      p_rsp_val => s_cs_rsp.req,
      p_rsp_ack => s_cs_rsp.ack,

      p_config_write => s_config_write,
      p_config_data => s_config_data,
      p_status => s_status
      );

  cmd_router: nsl_bnoc.routed.routed_router
    generic map(
      in_port_count => 1,
      out_port_count => 2,
      routing_table => (0 => 0, 1 => 1, others => 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_in_val(0) => s_from_host(1).req,
      p_in_ack(0) => s_from_host(1).ack,

      p_out_val(0) => s_routed_swd_cmd.req,
      p_out_val(1) => s_routed_cs_cmd.req,

      p_out_ack(0) => s_routed_swd_cmd.ack,
      p_out_ack(1) => s_routed_cs_cmd.ack
      );

  rsp_router: nsl_bnoc.routed.routed_router
    generic map(
      in_port_count => 2,
      out_port_count => 1,
      routing_table => (others => 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_in_val(0) => s_routed_swd_rsp.req,
      p_in_val(1) => s_routed_cs_rsp.req,

      p_in_ack(0) => s_routed_swd_rsp.ack,
      p_in_ack(1) => s_routed_cs_rsp.ack,
      
      p_out_val(0) => s_to_host(1).req,
      p_out_ack(0) => s_to_host(1).ack
      );

  cs_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val => s_routed_cs_cmd.req,
      p_cmd_in_ack => s_routed_cs_cmd.ack,
      p_rsp_out_val => s_routed_cs_rsp.req,
      p_rsp_out_ack => s_routed_cs_rsp.ack,

      p_cmd_out_val => s_cs_cmd.req,
      p_cmd_out_ack => s_cs_cmd.ack,
      p_rsp_in_val => s_cs_rsp.req,
      p_rsp_in_ack => s_cs_rsp.ack
      );

  swd_endpoint: nsl_bnoc.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val => s_routed_swd_cmd.req,
      p_cmd_in_ack => s_routed_swd_cmd.ack,
      p_rsp_out_val => s_routed_swd_rsp.req,
      p_rsp_out_ack => s_routed_swd_rsp.ack,

      p_cmd_out_val => s_swd_cmd.req,
      p_cmd_out_ack => s_swd_cmd.ack,
      p_rsp_in_val => s_swd_rsp.req,
      p_rsp_in_ack => s_swd_rsp.ack
      );

  process(s_sys_clk, s_sys_resetn_soft, s_config_write)
  begin
    if s_sys_resetn_soft = '0' then
      s_io_config <= (others => '0');
    elsif rising_edge(s_sys_clk) then
      if s_config_write(1) = '1' then
        s_io_config(0) <= s_config_data(0);
      end if;

      if s_config_write(2) = '1' then
        s_io_config(1) <= s_config_data(0);
      end if;
    end if;
  end process;
  
  s_status(1)(0) <= dbg_srst;
  s_status(1)(1) <= dbg_trst;
  s_status(2) <= std_ulogic_vector(to_unsigned(sys_clk_hz, s_status(2)'length)); -- s_sys_clk
  s_srst <= s_io_config(0);
  s_trst <= s_io_config(1);

  monitor: util.activity.activity_monitor
    generic map(
      blink_time => sys_clk_hz / 8
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,
      p_togglable => s_invalid_input,--dbg_tms,
      p_activity => user_led
      );
  
  dbg_trst <= '0' when s_trst = '1' else 'Z';
  dbg_tdi <= 'L';
  dbg_tms <= swd_o.dio.v when swd_o.dio.en = '1' else 'Z';
  dbg_tck <= swd_o.clk;
  dbg_srst <= '0' when s_srst = '1' else 'Z';

  io_en <= '1';
  jtag_en <= '0';

end arch;
