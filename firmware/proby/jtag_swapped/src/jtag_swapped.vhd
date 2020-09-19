library ieee;
use ieee.std_logic_1164.all;

library nsl_indication;

entity top is
  port (
    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    clk: in std_ulogic;

    io_en: inout std_ulogic;
    jtag_en: inout std_ulogic;

    dbg_spare: out std_ulogic;
    dbg_srst: inout std_ulogic;
    dbg_tdo: out std_ulogic;
    dbg_rtck: in std_ulogic;
    dbg_tck: out std_ulogic;
    dbg_tms: inout std_ulogic;
    dbg_tdi: in std_ulogic;
    dbg_trst: inout std_ulogic;

    ftdi_tck: in std_ulogic;
    ftdi_tdi: in std_ulogic;
    ftdi_tdo: out std_ulogic;
    ftdi_tms: in std_ulogic;
    ftdi_d4: in std_ulogic;
    ftdi_d5: in std_ulogic;
    ftdi_d6: out std_ulogic;
    ftdi_d7: out std_ulogic;
    ftdi_c0: in std_ulogic;
    ftdi_c1: in std_ulogic;
    ftdi_c2: in std_ulogic;
    ftdi_c3: out std_ulogic;
    ftdi_c5: inout std_ulogic;
    ftdi_c6: inout std_ulogic
  );
end top;

architecture arch of top is
  
begin

  --        JTAG Mapping:    SWD Mapping:
  -- D0    -> TCK           -> SWCLK
  -- D1    -> TDI           -> SWDIO out
  -- D2    <- TDO           <- SWDIO in
  -- D3    -> TMS
  -- D4    -> TRST          -> Z
  -- D5                     -> SWDIO oe
  -- D6    <- SRST readback <- SRST readback
  -- D7    <- RTCK
  -- C0    -> SRST          -> SRST
  -- C1    -> Enable        -> Enable
  -- C2    -> 0             -> 1
  -- C3
  -- C4
  -- C5
  -- C6    -> Activity      -> Activity
  -- C7

  dbg_spare <= 'L';
  dbg_tck <= ftdi_tck;
  dbg_srst <= '0' when ftdi_c0 = '0' else 'Z';

  dbg_tms <= ftdi_tms;
  dbg_trst <= ftdi_d4;
  dbg_tdo <= ftdi_tdi;
  ftdi_tdo <= dbg_tdi;

  ftdi_d7 <= dbg_rtck;
  ftdi_d6 <= dbg_srst;
  ftdi_c3 <= 'H';
  
  monitor: nsl_indication.activity.activity_monitor
    generic map(
      blink_cycles_c => 12000000 / 8
      )
    port map(
      reset_n_i => '1',
      clock_i => clk,
      togglable_i => ftdi_tck,
      activity_o => user_led
      );
  
  io_en <= ftdi_c1;
  jtag_en <= '0';

end arch;
