library ieee;
use ieee.std_logic_1164.all;

library nsl_io, nsl_i2c, nsl_ftdi;

package topcell is

  component wrapper
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
      dbg_tdi: inout std_logic;
      dbg_tdo: inout std_logic;
      dbg_trst: inout std_logic;

      scl: inout std_logic;
      sda: inout std_logic;

      fifo_data: inout std_logic_vector(7 downto 0);
      fifo_rxfn: in std_ulogic;
      fifo_txen: in std_ulogic;
      fifo_rdn: out std_ulogic;
      fifo_wrn: out std_ulogic;
      fifo_oen: out std_ulogic;
      fifo_clk: in std_ulogic
      );
  end component;

  component main
    generic(
      sys_clk_hz : natural
      );
    port (
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
  end component;

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

end package;
