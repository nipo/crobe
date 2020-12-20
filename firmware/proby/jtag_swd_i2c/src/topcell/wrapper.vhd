library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library nsl_i2c, nsl_ftdi, nsl_io, nsl_hwdep;
library design;

entity wrapper is
  port (
    clk: in std_ulogic;

    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    io_en: out std_ulogic;
    jtag_en: out std_ulogic;

    dbg_spare: in std_ulogic;
    dbg_srst: inout std_logic;
    dbg_rtck: in std_ulogic;
    dbg_tck: out std_ulogic;
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
end wrapper;

architecture arch of wrapper is
  
  constant sys_clk_hz : natural := 900000000 / 9;
  signal s_sys_clk, s_sys_resetn : std_ulogic;

  signal button_pressed : std_ulogic;

  signal dbg_srst_o: nsl_io.io.opendrain;
  signal dbg_tms_o: nsl_io.io.directed;
  signal dbg_tdi_o: nsl_io.io.directed;
  signal dbg_tdo_o: nsl_io.io.directed;
  signal dbg_trst_o: nsl_io.io.directed;
  signal dbg_srst_i: std_ulogic;
  signal dbg_tms_i: std_ulogic;
  signal dbg_tdi_i: std_ulogic;
  signal dbg_tdo_i: std_ulogic;
  signal dbg_trst_i: std_ulogic;
  signal i2c_o : nsl_i2c.i2c.i2c_o;
  signal i2c_i : nsl_i2c.i2c.i2c_i;
  signal ft245_i : nsl_ftdi.ft245.ft245_sync_fifo_master_i;
  signal ft245_o : nsl_ftdi.ft245.ft245_sync_fifo_master_o;

  signal pll_resetn : std_ulogic;
  
begin

  reset_gen: nsl_hwdep.reset.reset_at_startup
    port map(
      clock_i => clk,
      reset_n_o => pll_resetn
      );
  
  sys_clk_gen: design.topcell.clk_gen
    generic map(
      sys_clk_hz => sys_clk_hz
      )
    port map(
      p_clk_12 => clk,
      p_resetn => pll_resetn,
      p_sys_clk => s_sys_clk,
      p_sys_clk_ready => s_sys_resetn
      );

  button_pressed <= not user_btn;
  
  main_inst: design.topcell.main
    generic map(
      sys_clk_hz => sys_clk_hz
      )
    port map(
      sys_clk => s_sys_clk,
      sys_resetn => s_sys_resetn,

      user_led => user_led,
      button_pressed => button_pressed,

      dbg_srst_o => dbg_srst_o,
      dbg_srst_i => dbg_srst_i,
      dbg_tms_o => dbg_tms_o,
      dbg_tms_i => dbg_tms_i,
      dbg_tdi_o => dbg_tdi_o,
      dbg_tdi_i => dbg_tdi_i,
      dbg_tdo_o => dbg_tdo_o,
      dbg_tdo_i => dbg_tdo_i,
      dbg_tck_o => dbg_tck,
      dbg_trst_o => dbg_trst_o,
      dbg_trst_i => dbg_trst_i,

      i2c_o  => i2c_o,
      i2c_i  => i2c_i,

      ft245_i  => ft245_i,
      ft245_o  => ft245_o
      );

  i2c_driver: nsl_i2c.i2c.i2c_line_driver
    port map(
      bus_io.scl => scl,
      bus_io.sda => sda,
      bus_o => i2c_i,
      bus_i => i2c_o
      );

  ft245_driver: nsl_ftdi.ft245.ft245_sync_fifo_master_driver
    port map(
      bus_o => ft245_i,
      bus_i => ft245_o,

      ft245_clk_i => fifo_clk,
      ft245_data_io => fifo_data,
      ft245_rxf_n_i => fifo_rxfn,
      ft245_txe_n_i => fifo_txen,
      ft245_rd_n_o => fifo_rdn,
      ft245_wr_n_o => fifo_wrn,
      ft245_oe_n_o => fifo_oen
      );

  srst_driver: nsl_io.io.opendrain_io_driver
    port map(
      v_i => dbg_srst_o,
      v_o => dbg_srst_i,
      io_io => dbg_srst
      );

  tdi_driver: nsl_io.io.directed_io_driver
    port map(
      v_i => dbg_tdi_o,
      v_o => dbg_tdi_i,
      io_io => dbg_tdi
      );

  tdo_driver: nsl_io.io.directed_io_driver
    port map(
      v_i => dbg_tdo_o,
      v_o => dbg_tdo_i,
      io_io => dbg_tdo
      );

  tms_driver: nsl_io.io.directed_io_driver
    port map(
      v_i => dbg_tms_o,
      v_o => dbg_tms_i,
      io_io => dbg_tms
      );

  trst_driver: nsl_io.io.directed_io_driver
    port map(
      v_i => dbg_trst_o,
      v_o => dbg_trst_i,
      io_io => dbg_trst
      );
  
  io_en <= '1';
  jtag_en <= '0';

end arch;
