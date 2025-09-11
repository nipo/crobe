target = jtag_spi
top = work.gowin.boundary
work-srcdir = $(SRC_DIR)/../src
target_part_name = GW1N-9C
target_part = GW1N-UV9UG256C6/I5
hwdep = gowin
tool = gowin
gowin-use-as-gpio = sspi done ready cpu mspi

fw_dest = ../../../crobe/component/gowin/fw/0x0100481b.fs.gz

all: $(fw_dest)

$(fw_dest): $(target).fs.gz
	mkdir -p $(dir $(fw_dest))
	cp $< $@

$(target).fs.gz: $(target).fs
	gzip -fk $<

include $(NSL)/build/build.mk
