library ieee;
use ieee.std_logic_1164.all;

package topcell is

  component clk_gen is
    generic(
      sys_clk_hz : natural
      );
    port(
      p_clk_12        : in  std_ulogic;
      p_resetn        : in  std_ulogic;
      p_sys_clk       : out std_ulogic;
      p_sys_clk_ready : out std_ulogic
      );
  end component;

  component swd_dp
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
  end component;

end package;
