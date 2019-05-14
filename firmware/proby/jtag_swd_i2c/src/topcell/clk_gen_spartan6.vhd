library ieee;
use ieee.std_logic_1164.all;

library unisim;

entity clk_gen is
  generic(
    sys_clk_hz : natural
    );
  port(
    p_clk_12        : in  std_ulogic;
    p_resetn        : in  std_ulogic;
    p_sys_clk       : out std_ulogic;
    p_sys_clk_ready : out std_ulogic
    );
end entity;

architecture spartan6 of clk_gen is
  signal s_reset_dcm, s_reset_pll         : std_ulogic;
  signal s_sys_clk, s_pll_locked, s_clkfb : std_ulogic;
  signal s_clk_60, s_dcm_locked           : std_ulogic;
begin

  s_reset_dcm <= not p_resetn;
  s_reset_pll <= not s_dcm_locked;
  
  core_clk60_gen: unisim.vcomponents.dcm_sp
    generic map(
      clkin_period => 83.333, -- 12MHz
      clkfx_multiply => 5,
      clkfx_divide => 1,
      clkin_divide_by_2 => false
      )
    port map(
      clkin => p_clk_12,
      rst => s_reset_dcm,
      clkfx => s_clk_60,
      locked => s_dcm_locked
      );
  
  core_clock_gen: unisim.vcomponents.pll_base
    generic map (
      clk_feedback         => "CLKFBOUT",
      divclk_divide        => 1,
      clkfbout_mult        => 15, -- 900 MHz
      clkout0_divide       => 900000000 / sys_clk_hz,
      clkin_period         => 16.667,
      ref_jitter           => 0.125
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

  sys_clk_buffer: unisim.vcomponents.bufg
    port map(
      i => s_sys_clk,
      o => p_sys_clk
      );
  
  p_sys_clk_ready <= s_pll_locked and s_dcm_locked;

end architecture;
