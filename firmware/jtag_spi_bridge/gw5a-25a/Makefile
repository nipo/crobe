target = jtag_spi
top = work.gowin.boundary
work-srcdir = $(SRC_DIR)/../src
target_part_name = GW5A-25A
target_part = GW5A-LV25MG121NC1/I0
hwdep = gowin
tool = gowin
gowin-use-as-gpio = sspi done ready cpu mspi

fw_dest = ../../../crobe/component/gowin/fw/0x0001281b_jtag_spi.fs.gz

all: $(fw_dest)

$(fw_dest): $(target).fs.gz
	mkdir -p $(dir $(fw_dest))
	cp $< $@

$(target).fs.gz: $(target).fs
	gzip -fk $<

include $(NSL)/build/build.mk
