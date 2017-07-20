library ieee;
use ieee.std_logic_1164.all;

package topcell is

  component swd_dp
    port (
      clk: in std_ulogic;

      user_led: out std_ulogic;
      user_btn: in std_ulogic;

      io_en: out std_ulogic;
      io0: inout std_logic_vector(7 downto 0);
      io1: in std_ulogic_vector(23 downto 0);

      jtag_en: out std_ulogic;
      jtag_tdi: in std_ulogic;
      jtag_tms: in std_ulogic;
      jtag_tdo: out std_ulogic;
      jtag_tck: in std_ulogic;

      fifo_data: inout std_logic_vector(7 downto 0);
      fifo_rxfn: in std_ulogic;
      fifo_txen: in std_ulogic;
      fifo_rdn: out std_ulogic;
      fifo_wrn: out std_ulogic;
      fifo_oen: out std_ulogic;
      fifo_clk: in std_ulogic;

      ram_addr: out std_ulogic_vector(21 downto 0);
      ram_da: inout std_ulogic_vector(7 downto 0);
      ram_db: inout std_ulogic_vector(7 downto 0);
      ram_dap: inout std_ulogic;
      ram_dbp: inout std_ulogic;
      ram_bwan: out std_ulogic;
      ram_bwbn: out std_ulogic;
      ram_wen: out std_ulogic;
      ram_cen: out std_ulogic;
      ram_cenn: out std_ulogic;
      ram_oen: out std_ulogic;
      ram_clk: out std_ulogic
      );
  end component;

end package;
