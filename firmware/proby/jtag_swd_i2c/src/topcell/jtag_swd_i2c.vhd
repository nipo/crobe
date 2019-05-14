library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library util, nsl, coresight, signalling, work;

entity jtag_swd_i2c is
  port (
    clk: in std_ulogic;

    user_led: out std_ulogic;
    user_btn: in std_ulogic;

    io_en: out std_ulogic;
    jtag_en: out std_ulogic;

    dbg_spare: in std_logic;
    dbg_srst: inout std_logic;
    dbg_rtck: in std_logic;
    dbg_tck: out std_logic;
    dbg_tms: inout std_logic;
    dbg_tdi: out std_logic;
    dbg_tdo: in std_logic;
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
end jtag_swd_i2c;

architecture arch of jtag_swd_i2c is

  constant cs_reg_count : natural := 4;
  
  signal s_fifo_resetn, s_sys_resetn : std_ulogic;
  signal s_fifo_clk : std_ulogic;
  signal s_sys_clk : std_ulogic;
  signal s_sys_resetn_soft, s_resetn_soft_async, s_invalid_input: std_ulogic;
  
  signal s_from_host, s_to_host : nsl.framed.framed_bus_array(1 downto 0);
  signal s_from_host_sized, s_to_host_sized : nsl.sized.sized_bus;

  type endpoint_comm is
  record
    routed_cmd, routed_rsp : nsl.routed.routed_bus;
    framed_cmd, framed_rsp : nsl.framed.framed_bus;
  end record;

  signal comm_swd, comm_i2c, comm_cs, comm_jtag : endpoint_comm;
  signal swd_o : signalling.swd.swd_master_c;
  signal swd_i : signalling.swd.swd_master_s;
  signal jtag_o : signalling.jtag.jtag_ate_o;
  signal jtag_i : signalling.jtag.jtag_ate_i;
  
  signal s_srst, s_trst : std_ulogic;

  signal jtag_mode: std_ulogic;
  
  signal s_config_data: nsl.cs.cs_reg;
  signal s_config_write: std_ulogic_vector(cs_reg_count-1 downto 0);
  signal s_status: nsl.cs.cs_reg_array(cs_reg_count-1 downto 0);
  signal s_i2c_o: signalling.i2c.i2c_o;
  signal s_i2c_i: signalling.i2c.i2c_i;
  
  constant sys_clk_hz : natural := 900000000 / 6;

begin

  s_resetn_soft_async <= s_sys_resetn and not s_invalid_input and user_btn;

  sys_clk_gen: work.topcell.clk_gen
    generic map(
      sys_clk_hz => sys_clk_hz
      )
    port map(
      p_clk_12 => clk,
      p_resetn => user_btn,
      p_sys_clk => s_sys_clk,
      p_sys_clk_ready => s_sys_resetn
      );

  reset_sync_fifo: util.sync.sync_rising_edge
    port map(
      p_clk => s_fifo_clk,
      p_in => s_sys_resetn,
      p_out => s_fifo_resetn
      );

  reset_sync: util.sync.sync_rising_edge
    port map(
      p_clk => s_sys_clk,
      p_in => s_resetn_soft_async,
      p_out => s_sys_resetn_soft
      );
  
  ftdi_split: nsl.ftdi.ft245_sync_fifo_master
    generic map(
      burst_length => 64
      )
    port map(
      p_clk => s_fifo_clk,
      p_resetn => s_fifo_resetn,

      p_ftdi_clk => fifo_clk,
      p_ftdi_data => fifo_data,
      p_ftdi_rxfn => fifo_rxfn,
      p_ftdi_txen => fifo_txen,
      p_ftdi_rdn => fifo_rdn,
      p_ftdi_wrn => fifo_wrn,
      p_ftdi_oen => fifo_oen,

      p_in_ready => s_from_host_sized.ack.ready,
      p_in_valid => s_from_host_sized.req.valid,
      p_in_data => s_from_host_sized.req.data,

      p_out_ready => s_to_host_sized.ack.ready,
      p_out_valid => s_to_host_sized.req.valid,
      p_out_data => s_to_host_sized.req.data
      );

  to_framed: nsl.sized.sized_to_framed
    port map(
      p_resetn => s_fifo_resetn,
      p_clk => s_fifo_clk,

      p_inval => s_invalid_input,
      
      p_in_val => s_from_host_sized.req,
      p_in_ack => s_from_host_sized.ack,

      p_out_val => s_from_host(0).req,
      p_out_ack => s_from_host(0).ack
      );

  from_framed: nsl.sized.sized_from_framed
    generic map(
      max_txn_length => 2048
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_fifo_clk,

      p_in_val => s_to_host(0).req,
      p_in_ack => s_to_host(0).ack,

      p_out_val => s_to_host_sized.req,
      p_out_ack => s_to_host_sized.ack
      );
  
  cmd_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => s_fifo_clk,
      p_clk(1) => s_sys_clk,

      p_in_val => s_from_host(0).req,
      p_in_ack => s_from_host(0).ack,

      p_out_val => s_from_host(1).req,
      p_out_ack => s_from_host(1).ack
      );
  
  rsp_fifo: nsl.framed.framed_fifo
    generic map(
      depth => 2048,
      clk_count => 2
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk(0) => s_sys_clk, -- input is port 0
      p_clk(1) => s_fifo_clk,

      p_in_val => s_to_host(1).req,
      p_in_ack => s_to_host(1).ack,

      p_out_val => s_to_host(0).req,
      p_out_ack => s_to_host(0).ack
      );

  cmd_router: nsl.routed.routed_router
    generic map(
      in_port_count => 1,
      out_port_count => 4,
      routing_table => (0, 1, 2, 3,
                        0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,
      p_in_val(0) => s_from_host(1).req,
      p_in_ack(0) => s_from_host(1).ack,
      p_out_val(0) => comm_swd.routed_cmd.req,
      p_out_val(1) => comm_jtag.routed_cmd.req,
      p_out_val(2) => comm_i2c.routed_cmd.req,
      p_out_val(3) => comm_cs.routed_cmd.req,
      p_out_ack(0) => comm_swd.routed_cmd.ack,
      p_out_ack(1) => comm_jtag.routed_cmd.ack,
      p_out_ack(2) => comm_i2c.routed_cmd.ack,
      p_out_ack(3) => comm_cs.routed_cmd.ack
      );

  rsp_router: nsl.routed.routed_router
    generic map(
      in_port_count => 4,
      out_port_count => 1,
      routing_table => (0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0,
                        0, 0, 0, 0)
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,
      p_out_val(0) => s_to_host(1).req,
      p_out_ack(0) => s_to_host(1).ack,
      p_in_val(0) => comm_swd.routed_rsp.req,
      p_in_val(1) => comm_jtag.routed_rsp.req,
      p_in_val(2) => comm_i2c.routed_rsp.req,
      p_in_val(3) => comm_cs.routed_rsp.req,
      p_in_ack(0) => comm_swd.routed_rsp.ack,
      p_in_ack(1) => comm_jtag.routed_rsp.ack,
      p_in_ack(2) => comm_i2c.routed_rsp.ack,
      p_in_ack(3) => comm_cs.routed_rsp.ack
      );

  swd_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val  => comm_swd.routed_cmd.req,
      p_cmd_in_ack  => comm_swd.routed_cmd.ack,
      p_rsp_out_val => comm_swd.routed_rsp.req,
      p_rsp_out_ack => comm_swd.routed_rsp.ack,

      p_cmd_out_val  => comm_swd.framed_cmd.req,
      p_cmd_out_ack  => comm_swd.framed_cmd.ack,
      p_rsp_in_val => comm_swd.framed_rsp.req,
      p_rsp_in_ack => comm_swd.framed_rsp.ack
      );

  jtag_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val  => comm_jtag.routed_cmd.req,
      p_cmd_in_ack  => comm_jtag.routed_cmd.ack,
      p_rsp_out_val => comm_jtag.routed_rsp.req,
      p_rsp_out_ack => comm_jtag.routed_rsp.ack,

      p_cmd_out_val  => comm_jtag.framed_cmd.req,
      p_cmd_out_ack  => comm_jtag.framed_cmd.ack,
      p_rsp_in_val => comm_jtag.framed_rsp.req,
      p_rsp_in_ack => comm_jtag.framed_rsp.ack
      );

  i2c_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val  => comm_i2c.routed_cmd.req,
      p_cmd_in_ack  => comm_i2c.routed_cmd.ack,
      p_rsp_out_val => comm_i2c.routed_rsp.req,
      p_rsp_out_ack => comm_i2c.routed_rsp.ack,

      p_cmd_out_val  => comm_i2c.framed_cmd.req,
      p_cmd_out_ack  => comm_i2c.framed_cmd.ack,
      p_rsp_in_val => comm_i2c.framed_rsp.req,
      p_rsp_in_ack => comm_i2c.framed_rsp.ack
      );

  cs_endpoint: nsl.routed.routed_endpoint
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,

      p_cmd_in_val  => comm_cs.routed_cmd.req,
      p_cmd_in_ack  => comm_cs.routed_cmd.ack,
      p_rsp_out_val => comm_cs.routed_rsp.req,
      p_rsp_out_ack => comm_cs.routed_rsp.ack,

      p_cmd_out_val  => comm_cs.framed_cmd.req,
      p_cmd_out_ack  => comm_cs.framed_cmd.ack,
      p_rsp_in_val => comm_cs.framed_rsp.req,
      p_rsp_in_ack => comm_cs.framed_rsp.ack
      );
  
  dp: coresight.dp.dp_framed_swdp
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,
      
      p_cmd_val => comm_swd.framed_cmd.req,
      p_cmd_ack => comm_swd.framed_cmd.ack,

      p_rsp_val => comm_swd.framed_rsp.req,
      p_rsp_ack => comm_swd.framed_rsp.ack,
      
      p_swd_c => swd_o,
      p_swd_s => swd_i
      );

  i2c: nsl.i2c.i2c_framed_ctrl
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,

      p_cmd_val => comm_i2c.framed_cmd.req,
      p_cmd_ack => comm_i2c.framed_cmd.ack,
      p_rsp_val => comm_i2c.framed_rsp.req,
      p_rsp_ack => comm_i2c.framed_rsp.ack,

      p_i2c_o => s_i2c_o,
      p_i2c_i => s_i2c_i
      );

  scl_driver: signalling.io.od_std_logic_driver
    port map(
      control => s_i2c_o.scl,
      status => s_i2c_i.scl,
      io => scl
      );

  sda_driver: signalling.io.od_std_logic_driver
    port map(
      control => s_i2c_o.sda,
      status => s_i2c_i.sda,
      io => sda
      );

  ate: nsl.jtag.jtag_framed_ate
    port map(
      clock_i  => s_sys_clk,
      reset_n_i => s_sys_resetn_soft,
      
      cmd_i => comm_jtag.framed_cmd.req,
      cmd_o => comm_jtag.framed_cmd.ack,
      rsp_o => comm_jtag.framed_rsp.req,
      rsp_i => comm_jtag.framed_rsp.ack,

      tck_o => jtag_o.tck,
      tdi_o => jtag_o.tdi,
      tdo_i => jtag_i.tdo,
      tms_o => jtag_o.tms
      );

  cs: nsl.cs.cs_framed_reg
    generic map(
      config_count => s_config_write'length,
      status_count => s_status'length
      )
    port map(
      p_clk  => s_sys_clk,
      p_resetn => s_sys_resetn_soft,
      
      p_cmd_val => comm_cs.framed_cmd.req,
      p_cmd_ack => comm_cs.framed_cmd.ack,

      p_rsp_val => comm_cs.framed_rsp.req,
      p_rsp_ack => comm_cs.framed_rsp.ack,

      p_config_write => s_config_write,
      p_config_data => s_config_data,
      p_status => s_status
      );

  process(s_sys_clk, s_sys_resetn_soft, s_config_write)
  begin
    if s_sys_resetn_soft = '0' then
      s_srst <= '0';
      s_trst <= '0';
      jtag_mode <= '0';
    elsif rising_edge(s_sys_clk) then
      if s_config_write(1) = '1' then
        s_srst <= s_config_data(0);
      end if;

      if s_config_write(2) = '1' then
        s_trst <= s_config_data(0);
      end if;

      if s_config_write(3) = '1' then
        jtag_mode <= s_config_data(0);
      end if;
    end if;
  end process;
  
  s_status(0) <= std_ulogic_vector(to_unsigned(sys_clk_hz, s_status(0)'length)); -- s_sys_clk
  s_status(1)(0) <= dbg_srst;
  s_status(2)(0) <= dbg_trst;
  s_status(3)(0) <= jtag_mode;

  ios: process(jtag_o, jtag_mode, swd_o, s_trst, s_srst)
  begin
    dbg_trst <= 'Z';
    dbg_srst <= 'Z';
    dbg_tdi <= 'L';
    dbg_tms <= 'Z';
    dbg_tck <= '0';

    if s_trst = '1' then
      dbg_trst <= '0';
    end if;

    if s_srst = '1' then
      dbg_srst <= '0';
    end if;
      
    if jtag_mode = '1' then
      dbg_tdi <= jtag_o.tdi;
      dbg_tms <= jtag_o.tms;
      dbg_tck <= jtag_o.tck;
    else
      dbg_tdi <= '0';
      if swd_o.dio.en = '1' then
        dbg_tms <= swd_o.dio.v;
      end if;
      dbg_tck <= swd_o.clk;
    end if;
  end process;
  
  swd_i.dio.v <= dbg_tms;
  jtag_i.tdo <= dbg_tdo;

  io_en <= '1';
  jtag_en <= '0';

  monitor: util.activity.activity_monitor
    generic map(
      blink_time => sys_clk_hz / 8
      )
    port map(
      p_resetn => s_sys_resetn_soft,
      p_clk => s_sys_clk,
      p_togglable => dbg_tms,
      p_activity => user_led
      );

end arch;
