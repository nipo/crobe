library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb is
end tb;

library nsl;
use nsl.sized.all;

library testing;
use testing.sized.all;
use testing.ftdi.all;

library top;
use top.topcell.all;

architecture arch of tb is

  signal s_clk: std_ulogic := '0';

  signal s_resetn: std_ulogic := '0';

  signal s_user_btn: std_ulogic;

  signal s_io0: std_logic_vector(7 downto 0);

  signal s_fifo_data: std_logic_vector(7 downto 0);
  signal s_fifo_rxfn: std_ulogic;
  signal s_fifo_txen: std_ulogic;
  signal s_fifo_rdn: std_ulogic;
  signal s_fifo_wrn: std_ulogic;
  signal s_fifo_oen: std_ulogic;
  signal s_fifo_clk: std_ulogic := '0';

  signal s_gen_ack, s_chk_ack : nsl.sized.sized_ack;
  signal s_gen_val, s_chk_val : nsl.sized.sized_req;

  signal s_done : std_ulogic_vector(1 downto 0) := "00";
  
  signal s_ap_resetn : std_ulogic;
  signal s_ap_sel : unsigned(7 downto 0);
  signal s_ap_a : unsigned(5 downto 0);
  signal s_ap_rdata : unsigned(31 downto 0);
  signal s_ap_ready : std_ulogic;
  signal s_ap_rok : std_ulogic;
  signal s_ap_ren : std_ulogic;
  signal s_ap_wdata : unsigned(31 downto 0);
  signal s_ap_wen : std_ulogic;

begin

  reset_gen: process
  begin
    s_resetn <= '0';
    wait for 100 ns;
    s_resetn <= '1';
    wait;
  end process;
  
  clock_gen: process(s_clk)
  begin
    if s_done /= (s_done'range => '1') then
      s_clk <= not s_clk after 41.66 ns;
    end if;
  end process;

  wait_done: process(s_done)
  begin
    if s_done = (s_done'range => '1') then
      assert false report "Done !" severity note;
    end if;
  end process;

  fifo_clock_gen: process(s_fifo_clk)
  begin
    if s_done /= (s_done'range => '1') then
      s_fifo_clk <= not s_fifo_clk after 8.333 ns;
    end if;
  end process;

  t: top.topcell.swd_dp
    port map(
      clk => s_clk,
      user_led => open,
      user_btn => '1',
      io_en => open,
      io0 => s_io0,
      io1 => "LLLLLLLLLLLLLLLLLLLLLLLL",
      jtag_en => open,
      jtag_tdi => '0',
      jtag_tms => '0',
      jtag_tdo => open,
      jtag_tck => '0',

      fifo_data => s_fifo_data,
      fifo_rxfn => s_fifo_rxfn,
      fifo_txen => s_fifo_txen,
      fifo_rdn => s_fifo_rdn,
      fifo_wrn => s_fifo_wrn,
      fifo_oen => s_fifo_oen,
      fifo_clk => s_fifo_clk,

      ram_addr => open,
      ram_da => open,
      ram_db => open,
      ram_dap => open,
      ram_dbp => open,
      ram_bwan => open,
      ram_bwbn => open,
      ram_wen => open,
      ram_cen => open,
      ram_cenn => open,
      ram_oen => open,
      ram_clk => open
      );

  split: testing.ftdi.ft245_sync_fifo_merger
    port map(
      p_clk => s_fifo_clk,
      p_data => s_fifo_data,
      p_rxfn => s_fifo_rxfn,
      p_txen => s_fifo_txen,
      p_rdn => s_fifo_rdn,
      p_wrn => s_fifo_wrn,
      p_oen => s_fifo_oen,

      p_out_read => s_chk_ack.ack,
      p_out_empty_n => s_chk_val.val,
      p_out_data => s_chk_val.data,

      p_in_full_n => s_gen_ack.ack,
      p_in_write => s_gen_val.val,
      p_in_data => s_gen_val.data
      );

  chk: testing.sized.sized_file_checker
    generic map(
      filename => "rsp.txt"
      )
    port map(
      p_clk => s_fifo_clk,
      p_resetn => s_resetn,

      p_in_val => s_chk_val,
      p_in_ack => s_chk_ack,

      p_done => s_done(0)
      );

  gen: testing.sized.sized_file_reader
    generic map(
      filename => "cmd.txt"
      )
    port map(
      p_clk => s_fifo_clk,
      p_resetn => s_resetn,

      p_out_val => s_gen_val,
      p_out_ack => s_gen_ack,

      p_done => s_done(1)
      );

  swdap: testing.swd.swdap
    port map(
      p_swclk => s_io0(4),
      p_swdio => s_io0(5),
      p_swd_resetn => s_ap_resetn,
      p_ap_sel => s_ap_sel,
      p_ap_a => s_ap_a,
      p_ap_rdata => s_ap_rdata,
      p_ap_ready => s_ap_ready,
      p_ap_ren => s_ap_ren,
      p_ap_rok => s_ap_rok,
      p_ap_wdata => s_ap_wdata,
      p_ap_wen => s_ap_wen
      );

  ap: testing.swd.ap_sim
    port map(
      p_clk => s_io0(4),
      p_resetn => s_ap_resetn,
      p_ap => s_ap_sel,
      p_a => s_ap_a,
      p_rdata => s_ap_rdata,
      p_ready => s_ap_ready,
      p_ren => s_ap_ren,
      p_rok => s_ap_rok,
      p_wdata => s_ap_wdata,
      p_wen => s_ap_wen
      );

  s_user_btn <= s_resetn;
  
end;
