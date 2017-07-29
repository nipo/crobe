library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library unisim;
use unisim.vcomponents.all;

library nsl;
use nsl.ftdi.all;
use nsl.routed.all;
use nsl.framed.all;
use nsl.util.all;
use nsl.sized.all;

library util;
use util.sync.sync_rising_edge;
use util.activity.activity_monitor;

library coresight;
use coresight.dp.all;

entity swd_dp is
  port (
    clk: in std_ulogic;

    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    io_en: out std_ulogic;

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

  signal s_resetn_fifo, s_reset_dcm, s_reset_pll : std_ulogic;
  signal s_sys_clk, s_pll_locked, s_clkfb : std_ulogic;
  signal s_clk_60, s_dcm_locked : std_ulogic;
  signal s_sys_resetn_soft, s_resetn_soft_async, s_invalid_input: std_ulogic;
  
  signal s_from_host_val, s_to_host_val : nsl.framed.framed_req_array(1 downto 0);
  signal s_from_host_ack, s_to_host_ack : nsl.framed.framed_ack_array(1 downto 0);
  signal s_from_host_sized_val, s_to_host_sized_val : nsl.sized.sized_req;
  signal s_from_host_sized_ack, s_to_host_sized_ack : nsl.sized.sized_ack;
  signal s_swd_cmd_val, s_swd_rsp_val : nsl.framed.framed_req;
  signal s_swd_cmd_ack, s_swd_rsp_ack : nsl.framed.framed_ack;
  signal s_routed_swd_cmd_val, s_routed_swd_rsp_val : nsl.routed.routed_req;
  signal s_routed_swd_cmd_ack, s_routed_swd_rsp_ack : nsl.routed.routed_ack;
  signal s_routed_cs_cmd_val, s_routed_cs_rsp_val : nsl.routed.routed_req;
  signal s_routed_cs_cmd_ack, s_routed_cs_rsp_ack : nsl.routed.routed_ack;
  signal s_cs_cmd_val, s_cs_rsp_val : nsl.framed.framed_req;
  signal s_cs_cmd_ack, s_cs_rsp_ack : nsl.framed.framed_ack;

  signal s_srst, s_trst, s_swclk, s_swdio_i, s_swdio_o, s_swdio_oe : std_ulogic;
  signal s_clk_gen, s_clk_gen_toggle: std_ulogic;
  
  signal s_io_config: std_ulogic_vector(1 downto 0);
  signal s_clk_gen_rate: unsigned(25 downto 0);
  signal s_config_data: nsl.cs.cs_reg;
  signal s_config_write: std_ulogic_vector(2 downto 0);
  signal s_status: nsl.cs.cs_reg_array(2 downto 0);

  constant sys_clk_mhz : natural := 150;
  
begin

  s_reset_dcm <= not user_btn;
  s_reset_pll <= not s_dcm_locked;
  s_resetn_soft_async <= s_pll_locked and s_dcm_locked and not s_invalid_input and user_btn;

  core_clk60_gen: dcm_sp
    generic map(
      clkin_period => 83.333, -- 12MHz
      clkfx_multiply => 5,
      clkfx_divide => 1,
      clkin_divide_by_2 => false
      )
    port map(
      clkin => clk,
      rst => s_reset_dcm,
      clkfx => s_clk_60,
      locked => s_dcm_locked
      );

  core_clock_gen: pll_base
    generic map (
        clk_feedback         => "CLKFBOUT",
        divclk_divide        => 1,
        clkfbout_mult        => 10, -- 600 MHz
        clkout0_divide       => 600 / sys_clk_mhz,
        clkin_period         => 16.667,
        ref_jitter           => 0.25
    )
    port map (
        clkfbout            => s_clkfb,
        clkout0             => s_sys_clk,
        clkout1             => open,
        clkout2             => open,
        clkout3             => open,
        clkout4             => open,
        clkout5             => open,
        locked              => s_pll_locked,
        rst                 => s_reset_pll,
        clkfbin             => s_clkfb,
        clkin               => s_clk_60
        );

  reset_sync_fifo: util.sync.sync_rising_edge
    port map(
      p_clk => fifo_clk,
      p_in => s_pll_locked,
      p_out => s_resetn_fifo
      );

  reset_sync: util.sync.sync_rising_edge
    port map(
      p_clk => s_sys_clk,
      p_in => s_resetn_soft_async,
      p_out => s_sys_resetn_soft
      );
  
  ftdi_split: nsl.ftdi.ft245_sync_fifo_splitter
    generic map(
      burst_length => 64
      )
    port map(
      p_clk => fifo_clk,
      p_resetn => s_resetn_fifo,

      p_ftdi_data => fifo_data,
      p_ftdi_rxfn => fifo_rxfn,
      p_ftdi_txen => fifo_txen,
      p_ftdi_rdn => fifo_rdn,
      p_ftdi_wrn => fifo_wrn,
      p_ftdi_oen => fifo_oen,

      p_in_read => s_from_host_sized_ack.ack,
      p_in_empty_n => s_from_host_sized_val.val,
      p_in_data => s_from_host_sized_val.data,

      p_out_full_n => s_to_host_sized_ack.ack,
      p_out_write => s_to_host_sized_val.val,
      p_out_data => s_to_host_sized_val.data
      );

  to_framed: nsl.sized.sized_to_framed
    port map(
      p_resetn => s_resetn_fifo,
      p_clk => fifo_clk,

      p_inval => s_invalid_input,
      
      p_in_val => s_from_host_sized_val,
      p_in_ack => s_from_host_sized_ack,

      p_out_val => s_from_host_val(0),
      p_out_ack => s_from_host_ack(0)
      );

  from_framed: nsl.sized.sized_from_framed
    generic map(
      max_txn_length => 2048
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => fifo_clk,

      p_in_val => s_to_host_val(0),
      p_in_ack => s_to_host_ack(0),

      p_out_val => s_to_host_sized_val,
      p_out_ack => s_to_host_sized_ack
      );
  
  cmd_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => fifo_clk,
      p_clk(1) => s_sys_clk,

      p_in_val => s_from_host_val(0),
      p_in_ack => s_from_host_ack(0),

      p_out_val => s_from_host_val(1),
      p_out_ack => s_from_host_ack(1)
      );
  
  rsp_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => s_sys_clk, -- input is port 0
      p_clk(1) => fifo_clk,

      p_in_val => s_to_host_val(1),
      p_in_ack => s_to_host_ack(1),

      p_out_val => s_to_host_val(0),
      p_out_ack => s_to_host_ack(0)
      );

  dp: coresight.dp.dp_framed_swdp
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,

      p_clk_ref => s_clk_gen,
      
      p_cmd_val => s_swd_cmd_val,
      p_cmd_ack => s_swd_cmd_ack,

      p_rsp_val => s_swd_rsp_val,
      p_rsp_ack => s_swd_rsp_ack,
      
      p_swclk => s_swclk,
      p_swdio_i => s_swdio_i,
      p_swdio_o => s_swdio_o,
      p_swdio_oe => s_swdio_oe
      );

  cs: nsl.cs.cs_framed_reg
    generic map(
      config_count => s_config_write'length,
      status_count => s_status'length
      )
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,
      
      p_cmd_val => s_cs_cmd_val,
      p_cmd_ack => s_cs_cmd_ack,

      p_rsp_val => s_cs_rsp_val,
      p_rsp_ack => s_cs_rsp_ack,

      p_config_write => s_config_write,
      p_config_data => s_config_data,
      p_status => s_status
      );

  cmd_router: nsl.routed.routed_router
    generic map(
      in_port_count => 1,
      out_port_count => 2,
      routing_table => (0 => 0, 1 => 1, others => 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_in_val(0) => s_from_host_val(1),
      p_in_ack(0) => s_from_host_ack(1),

      p_out_val(0) => s_routed_swd_cmd_val,
      p_out_val(1) => s_routed_cs_cmd_val,

      p_out_ack(0) => s_routed_swd_cmd_ack,
      p_out_ack(1) => s_routed_cs_cmd_ack
      );

  rsp_router: nsl.routed.routed_router
    generic map(
      in_port_count => 2,
      out_port_count => 1,
      routing_table => (others => 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_in_val(0) => s_routed_swd_rsp_val,
      p_in_val(1) => s_routed_cs_rsp_val,

      p_in_ack(0) => s_routed_swd_rsp_ack,
      p_in_ack(1) => s_routed_cs_rsp_ack,
      
      p_out_val(0) => s_to_host_val(1),
      p_out_ack(0) => s_to_host_ack(1)
      );

  cs_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val => s_routed_cs_cmd_val,
      p_cmd_in_ack => s_routed_cs_cmd_ack,
      p_rsp_out_val => s_routed_cs_rsp_val,
      p_rsp_out_ack => s_routed_cs_rsp_ack,

      p_cmd_out_val => s_cs_cmd_val,
      p_cmd_out_ack => s_cs_cmd_ack,
      p_rsp_in_val => s_cs_rsp_val,
      p_rsp_in_ack => s_cs_rsp_ack
      );

  swd_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val => s_routed_swd_cmd_val,
      p_cmd_in_ack => s_routed_swd_cmd_ack,
      p_rsp_out_val => s_routed_swd_rsp_val,
      p_rsp_out_ack => s_routed_swd_rsp_ack,

      p_cmd_out_val => s_swd_cmd_val,
      p_cmd_out_ack => s_swd_cmd_ack,
      p_rsp_in_val => s_swd_rsp_val,
      p_rsp_in_ack => s_swd_rsp_ack
      );

  clk_gen: nsl.util.baudrate_generator
    generic map(
      p_clk_rate => sys_clk_mhz * 1000000,
      rate_lsb => s_clk_gen_rate'low,
      rate_msb => s_clk_gen_rate'high
      )
    port map(
      p_clk => s_sys_clk,
      p_resetn => s_sys_resetn_soft,
      p_rate => s_clk_gen_rate,
      p_tick => s_clk_gen_toggle
      );

  process(s_sys_clk, s_sys_resetn_soft, s_config_write, s_clk_gen_toggle)
  begin
    if s_sys_resetn_soft = '0' then
      s_clk_gen_rate <= to_unsigned(1024 * 1024, s_clk_gen_rate'high+1)(s_clk_gen_rate'range);
      s_io_config <= (others => '0');
      s_clk_gen <= '0';
    elsif rising_edge(s_sys_clk) then
      if s_clk_gen_toggle = '1' then
        s_clk_gen <= not s_clk_gen;
      end if;

      if s_config_write(0) = '1' then
        s_clk_gen_rate <= unsigned(s_config_data(s_clk_gen_rate'range));
      end if;

      if s_config_write(1) = '1' then
        s_io_config(0) <= s_config_data(0);
      end if;

      if s_config_write(2) = '1' then
        s_io_config(1) <= s_config_data(0);
      end if;
    end if;
  end process;
  
  s_status(0)(s_clk_gen_rate'range) <= std_ulogic_vector(s_clk_gen_rate);
  s_status(1)(0) <= dbg_srst;
  s_status(1)(1) <= dbg_trst;
  s_status(2) <= std_ulogic_vector(to_unsigned(sys_clk_mhz * 1000000, s_status(2)'length)); -- s_sys_clk
  s_srst <= s_io_config(0);
  s_trst <= s_io_config(1);

  monitor: util.activity.activity_monitor
    generic map(
      blink_time => sys_clk_mhz * 1000000 / 8
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,
      p_togglable => dbg_tms,
      p_activity => user_led
      );
  
  s_swdio_i <= dbg_tms;
  dbg_trst <= '0' when s_trst = '1' else 'Z';
  dbg_tdi <= 'L';
  dbg_tms <= s_swdio_o when s_swdio_oe = '1' else 'Z';
  dbg_tck <= s_swclk;
  dbg_srst <= '0' when s_srst = '1' else 'Z';

  io_en <= '1';

end arch;
