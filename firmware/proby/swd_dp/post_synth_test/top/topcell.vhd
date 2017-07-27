library ieee;
use ieee.std_logic_1164.all;

package topcell is

  component swd_dp
    port (
      clk: in std_logic;

      user_led: out std_logic;
      user_btn: in std_logic;

      io_en: out std_logic;
      io0: inout std_logic_vector(7 downto 0);
      io1: in std_logic_vector(23 downto 0);

      jtag_en: out std_logic;
      jtag_tdi: in std_logic;
      jtag_tms: in std_logic;
      jtag_tdo: out std_logic;
      jtag_tck: in std_logic;

      fifo_data: inout std_logic_vector(7 downto 0);
      fifo_rxfn: in std_logic;
      fifo_txen: in std_logic;
      fifo_rdn: out std_logic;
      fifo_wrn: out std_logic;
      fifo_oen: out std_logic;
      fifo_clk: in std_logic;

      ram_addr: out std_logic_vector(21 downto 0);
      ram_da: inout std_logic_vector(7 downto 0);
      ram_db: inout std_logic_vector(7 downto 0);
      ram_dap: inout std_logic;
      ram_dbp: inout std_logic;
      ram_bwan: out std_logic;
      ram_bwbn: out std_logic;
      ram_wen: out std_logic;
      ram_cen: out std_logic;
      ram_cenn: out std_logic;
      ram_oen: out std_logic;
      ram_clk: out std_logic
      );
  end component;

end package;
