library ieee;
use ieee.std_logic_1164.all;
use work.all;

library unisim;
use unisim.vcomponents.all;

entity top is
  port (
    clk: in std_ulogic;

    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    io_en: out std_ulogic;
    io0: inout std_logic_vector(7 downto 0);
    io1: inout std_ulogic_vector(23 downto 0);

    jtag_en: out std_ulogic;
    jtag_tdi: in std_ulogic;
    jtag_tms: in std_ulogic;
    jtag_tdo: out std_ulogic;
    jtag_tck: in std_ulogic;

    fifo_data: inout std_logic_vector(7 downto 0);
    fifo_rxfn: in std_ulogic;
    fifo_txen: in std_ulogic;
    fifo_rdn: in std_ulogic;
    fifo_wrn: out std_ulogic;
    fifo_oen: in std_ulogic;
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
end top;

architecture arch of top is

  signal ft_tdi, ft_tms, ft_tck, ft_srst, ft_trst, ft_tdo, ft_rtck, ft_srst_in : std_logic;
  signal tp_tdi, tp_tms, tp_tck, tp_srst, tp_trst, tp_tdo, tp_rtck : std_logic;
  signal ft_activity, ft_jtag_en, ft_tms_oe : std_logic;

  signal r_design_id : std_ulogic_vector(31 downto 0);
  signal s_tap_dr_clk, s_tap_capture, s_tap_tdi : std_ulogic;

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
  -- C2    -> 1             -> 0
  -- C3
  -- C4
  -- C5
  -- C6    -> Activity      -> Activity
  -- C7

  io0(6) <= tp_tdi;
  io0(5) <= tp_tms;
  io0(4) <= tp_tck;
  io0(1) <= tp_srst;
  io0(7) <= tp_trst;
  io0(0) <= 'L';
  tp_tdo <= io0(2);
  tp_rtck <= io0(3);

  ft_tck <= fifo_data(0);
  ft_tdi <= fifo_data(1);
  ft_tms <= fifo_data(3);
  ft_trst <= fifo_data(4);
  ft_tms_oe <= fifo_data(5);
  ft_jtag_en <= not fifo_rdn;
  ft_activity <= fifo_oen;

  tp_tdi <= ft_tdi when ft_jtag_en = '1' else 'Z';

  tp_tms_gen: process(ft_tms, ft_jtag_en, ft_tdi)
  begin
    if ft_jtag_en = '1' then
      tp_tms <= ft_tms;
    else
      if ft_tms_oe = '1' then
        tp_tms <= ft_tdi;
      else
        tp_tms <= 'Z';
      end if;
    end if;
  end process;

  tp_tck <= ft_tck;
  tp_trst <= ft_trst when ft_jtag_en = '1' else 'Z';
  ft_tdo <= tp_tdo when ft_jtag_en = '1' else tp_tms;
  tp_srst <= '0' when ft_srst = '0' else 'Z';
  ft_rtck <= tp_rtck;
  ft_srst_in <= tp_srst;
  ft_srst <= fifo_rxfn;

  user_led <= ft_activity;

  io_en <= fifo_txen;
  io0(2) <= 'Z'; -- tdo
  io0(3) <= 'Z'; -- rtck

  io1 <= (others => 'L');

  jtag_en <= '0';
  jtag_tdo <= '0';

  fifo_data(0) <= 'Z';
  fifo_data(1) <= 'Z';
  fifo_data(2) <= ft_tdo;
  fifo_data(3) <= 'Z';
  fifo_data(4) <= 'Z';
  fifo_data(5) <= 'Z';
  fifo_data(6) <= ft_srst_in;
  fifo_data(7) <= ft_rtck;

  fifo_wrn <= '1';

  ram_addr <= (others => '0');
  ram_da <= (others => '0');
  ram_db <= (others => '0');
  ram_dap <= '0';
  ram_dbp <= '0';
  ram_bwan <= '1';
  ram_bwbn <= '1';
  ram_wen <= '1';
  ram_cen <= '1';
  ram_cenn <= '1';
  ram_oen <= '1';
  ram_clk <= '0';

   design_identifier : bscan_spartan6
   generic map (
      jtag_chain => 1
   )
   port map (
      capture => s_tap_capture,
      drck => s_tap_dr_clk,
      tdi => s_tap_tdi,
      tdo => r_design_id(0)
   );

  process(s_tap_dr_clk)
  begin
    if rising_edge(s_tap_dr_clk) then
      r_design_id <= s_tap_tdi & r_design_id(31 downto 1);

      if s_tap_capture = '1' then
        r_design_id <= x"bcc464b8";
      end if;
    end if;
  end process;

end arch;
