library ieee;
use ieee.std_logic_1164.all;

library unisim;

entity clk_gen is
  port(
    p_clk_12        : in  std_ulogic;
    p_resetn        : in  std_ulogic;
    p_sys_clk       : out std_ulogic;
    p_sys_clk_ready : out std_ulogic
    );
end entity;

architecture spartan6 of clk_gen is

  signal div : integer range 0 to 5;
  signal s_sys_clk : std_ulogic;

begin

  p_sys_clk_ready <= p_resetn;

  d: process(p_clk_12, p_resetn)
  begin
    if p_resetn = '0' then
      div <= 5;
      s_sys_clk <= '0';
    elsif rising_edge(p_clk_12) then
      if div = 0 then
        s_sys_clk <= not s_sys_clk;
        div <= 5;
      else
        div <= div - 1;
      end if;
    end if;
  end process;

  buf: unisim.vcomponents.bufg
    port map(
      i => s_sys_clk,
      o => p_sys_clk
      );
  
end architecture;
