library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library unisim;
use unisim.vcomponents.all;

library nsl;
use nsl.ftdi.all;
use nsl.routed.all;
use nsl.framed.all;
use nsl.sized.all;
use nsl.swd.all;

entity swd_dp is
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
end swd_dp;

architecture arch of swd_dp is

  signal s_resetn_fifo_clk, s_resetn : std_ulogic;
  
  signal s_from_host_val, s_to_host_val : nsl.framed.framed_req_array(1 downto 0);
  signal s_from_host_ack, s_to_host_ack : nsl.framed.framed_ack_array(1 downto 0);
  signal s_from_host_sized_val, s_to_host_sized_val : nsl.sized.sized_req;
  signal s_from_host_sized_ack, s_to_host_sized_ack : nsl.sized.sized_ack;
  signal s_swd_cmd_val, s_swd_rsp_val : nsl.framed.framed_req;
  signal s_swd_cmd_ack, s_swd_rsp_ack : nsl.framed.framed_ack;
  signal s_routed_swd_cmd_val, s_routed_swd_rsp_val : nsl.routed.routed_req;
  signal s_routed_swd_cmd_ack, s_routed_swd_rsp_ack : nsl.routed.routed_ack;
  signal s_routed_cs_cmd_val, s_routed_cs_rsp_val : nsl.routed.routed_req;
  signal s_routed_cs_cmd_ack, s_routed_cs_rsp_ack : nsl.routed.routed_ack;
  signal s_cs_cmd_val, s_cs_rsp_val : nsl.framed.framed_req;
  signal s_cs_cmd_ack, s_cs_rsp_ack : nsl.framed.framed_ack;

  signal s_srst, s_trst, s_swclk, s_swdio_i, s_swdio_o, s_swdio_oe : std_ulogic;
  signal s_soft_resetn, s_soft_reset: std_ulogic;

  signal s_io_config: std_ulogic_vector(2 downto 0);
  signal s_div: std_ulogic_vector(15 downto 0);
  signal s_config_data: nsl.cs.cs_reg;
  signal s_config_write: std_ulogic_vector(4 downto 0);
  signal s_status: nsl.cs.cs_reg_array(1 downto 0);
  
begin
  
  s_resetn <= user_btn;
  s_soft_resetn <= not s_soft_reset;

  reset_fifo_clk_sync: nsl.util.reset_synchronizer
    port map(
      p_resetn => s_resetn,
      p_resetn_sync => s_resetn_fifo_clk,
      p_clk => fifo_clk
      );
  
  ftdi_split: nsl.ftdi.ft245_sync_fifo_splitter
    generic map(
      burst_length => 64
      )
    port map(
      p_clk => fifo_clk,
      p_resetn => s_resetn_fifo_clk,

      p_ftdi_data => fifo_data,
      p_ftdi_rxfn => fifo_rxfn,
      p_ftdi_txen => fifo_txen,
      p_ftdi_rdn => fifo_rdn,
      p_ftdi_wrn => fifo_wrn,
      p_ftdi_oen => fifo_oen,

      p_in_read => s_from_host_sized_ack.ack,
      p_in_empty_n => s_from_host_sized_val.val,
      p_in_data => s_from_host_sized_val.data,

      p_out_full_n => s_to_host_sized_ack.ack,
      p_out_write => s_to_host_sized_val.val,
      p_out_data => s_to_host_sized_val.data
      );

  to_framed: nsl.sized.sized_to_framed
    port map(
      p_resetn => s_resetn_fifo_clk,
      p_clk => fifo_clk,

      p_inval => s_soft_reset,
      
      p_in_val => s_from_host_sized_val,
      p_in_ack => s_from_host_sized_ack,

      p_out_val => s_from_host_val(0),
      p_out_ack => s_from_host_ack(0)
      );

  from_framed: nsl.sized.sized_from_framed
    generic map(
      max_txn_length => 2048
      )
    port map(
      p_resetn => s_soft_resetn,
      p_clk => fifo_clk,

      p_in_val => s_to_host_val(0),
      p_in_ack => s_to_host_ack(0),

      p_out_val => s_to_host_sized_val,
      p_out_ack => s_to_host_sized_ack
      );
  
  cmd_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 1
      )
    port map(
      p_resetn => s_soft_resetn,
      p_clk(0) => fifo_clk,

      p_in_val => s_from_host_val(0),
      p_in_ack => s_from_host_ack(0),

      p_out_val => s_from_host_val(1),
      p_out_ack => s_from_host_ack(1)
      );
  
  rsp_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 16,
      clk_count => 1
      )
    port map(
      p_resetn => s_soft_resetn,
      p_clk(0) => fifo_clk,

      p_in_val => s_to_host_val(1),
      p_in_ack => s_to_host_ack(1),

      p_out_val => s_to_host_val(0),
      p_out_ack => s_to_host_ack(0)
      );

  dp: nsl.swd.swd_framed_dp
    port map(
      p_clk  => fifo_clk,
      p_resetn => s_soft_resetn,

      p_clk_div => unsigned(s_div),
      
      p_cmd_val => s_swd_cmd_val,
      p_cmd_ack => s_swd_cmd_ack,

      p_rsp_val => s_swd_rsp_val,
      p_rsp_ack => s_swd_rsp_ack,
      
      p_swclk => s_swclk,
      p_swdio_i => s_swdio_i,
      p_swdio_o => s_swdio_o,
      p_swdio_oe => s_swdio_oe
      );

  cs: nsl.cs.cs_framed_reg
    generic map(
      config_count => s_config_write'length,
      status_count => s_status'length
      )
    port map(
      p_clk  => fifo_clk,
      p_resetn => s_soft_resetn,
      
      p_cmd_val => s_cs_cmd_val,
      p_cmd_ack => s_cs_cmd_ack,

      p_rsp_val => s_cs_rsp_val,
      p_rsp_ack => s_cs_rsp_ack,

      p_config_write => s_config_write,
      p_config_data => s_config_data,
      p_status => s_status
      );

  cmd_router: nsl.routed.routed_router
    generic map(
      in_port_count => 1,
      out_port_count => 2,
      routing_table => (0 => 0, 1 => 1, others => 0)
      )
    port map(
      p_resetn => s_soft_resetn,
      p_clk => fifo_clk,

      p_in_val(0) => s_from_host_val(1),
      p_in_ack(0) => s_from_host_ack(1),

      p_out_val(0) => s_routed_swd_cmd_val,
      p_out_val(1) => s_routed_cs_cmd_val,

      p_out_ack(0) => s_routed_swd_cmd_ack,
      p_out_ack(1) => s_routed_cs_cmd_ack
      );

  rsp_router: nsl.routed.routed_router
    generic map(
      in_port_count => 2,
      out_port_count => 1,
      routing_table => (others => 0)
      )
    port map(
      p_resetn => s_soft_resetn,
      p_clk => fifo_clk,

      p_in_val(0) => s_routed_swd_rsp_val,
      p_in_val(1) => s_routed_cs_rsp_val,

      p_in_ack(0) => s_routed_swd_rsp_ack,
      p_in_ack(1) => s_routed_cs_rsp_ack,
      
      p_out_val(0) => s_to_host_val(1),
      p_out_ack(0) => s_to_host_ack(1)
      );

  cs_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_soft_resetn,
      p_clk => fifo_clk,

      p_cmd_in_val => s_routed_cs_cmd_val,
      p_cmd_in_ack => s_routed_cs_cmd_ack,
      p_rsp_out_val => s_routed_cs_rsp_val,
      p_rsp_out_ack => s_routed_cs_rsp_ack,

      p_cmd_out_val => s_cs_cmd_val,
      p_cmd_out_ack => s_cs_cmd_ack,
      p_rsp_in_val => s_cs_rsp_val,
      p_rsp_in_ack => s_cs_rsp_ack
      );

  swd_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_soft_resetn,
      p_clk => fifo_clk,

      p_cmd_in_val => s_routed_swd_cmd_val,
      p_cmd_in_ack => s_routed_swd_cmd_ack,
      p_rsp_out_val => s_routed_swd_rsp_val,
      p_rsp_out_ack => s_routed_swd_rsp_ack,

      p_cmd_out_val => s_swd_cmd_val,
      p_cmd_out_ack => s_swd_cmd_ack,
      p_rsp_in_val => s_swd_rsp_val,
      p_rsp_in_ack => s_swd_rsp_ack
      );

  process(fifo_clk, s_soft_resetn, s_config_write)
  begin
    if s_soft_resetn = '0' then
      s_div <= x"001D";
      s_io_config <= (others => '0');
    elsif rising_edge(fifo_clk) then
      if s_config_write(0) = '1' then
        s_div <= s_config_data(s_div'range);
      end if;

      if s_config_write(1) = '1' then
        s_io_config(0) <= s_config_data(0);
      end if;

      if s_config_write(2) = '1' then
        s_io_config(1) <= s_config_data(0);
      end if;

      if s_config_write(3) = '1' then
        s_io_config(2) <= s_config_data(0);
      end if;
    end if;
  end process;
  
  s_status(0)(15 downto 0) <= s_div;
  s_status(1)(0) <= io0(1); -- srst
  s_status(1)(1) <= io0(7); -- trst
  s_srst <= s_io_config(0);
  s_trst <= s_io_config(1);
  user_led <= s_io_config(2);
  
  s_swdio_i <= io0(5);
  io0(7) <= '0' when s_trst = '1' else 'Z'; -- TRST
  io0(6) <= 'L'; -- TDI
  io0(5) <= s_swdio_o when s_swdio_oe = '1' else 'Z'; -- TMS
  io0(4) <= s_swclk; -- TCK
  io0(3) <= 'L'; -- RTCK
  io0(2) <= 'L'; -- TDO
  io0(1) <= '0' when s_srst = '1' else 'Z'; -- SRST
  io0(0) <= 'L';
  
  jtag_en <= '0';
  jtag_tdo <= 'L';

  io_en <= '1';

--   user_led <= s_soft_resetn;
  
  -- RAM IO, unconnected
  
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

end arch;
