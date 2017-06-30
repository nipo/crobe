targets = efm32 nrf51 iap
arm-prefix = arm-mutekh-eabi-

efm32-src = efm32.c
efm32-sections = flash_erase flash_write
efm32-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
efm32-arch = arm

efm32g-src = efm32.c
efm32g-sections = flash_erase flash_write
efm32g-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC -DGECKO
efm32g-arch = arm

nrf51-src = nrf51.c
nrf51-sections = flash_erase flash_write
nrf51-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
nrf51-arch = arm

iap-src = iap.c
iap-sections = iap_call
iap-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
iap-arch = arm

target = ../../../../crobe/target/soc/arm_based/puppet_code.py

all: code.py

copy: $(target)

$(target): code.py
	cp $< $@

clean:
	rm -f $(clean-files)

code-files =
clean-files = code.py

define section_expand

$1-$2.py: $1.o
	> $$@
	echo -n "$1_$2 = b'" >> $$@
	$($($1-arch)-prefix)objcopy $$< -j .text.$2 -O binary /dev/stdout \
	| hexdump -v -e '/1 "_x%02x"' | tr _ "\\" >> $$@
	echo "'" >> $$@

all: $1-$2.py

clean-files += $1-$2.py
code-files += $1-$2.py

endef

define target_expand

$1.o: $($1-src) $(MAKEFILE_LIST)
	$($($1-arch)-prefix)gcc -c -o $$@ $$< $($(1)-cflags) -ffunction-sections

clean-files += $1.o

$(eval $(foreach s,$($1-sections),$(call section_expand,$1,$s)))

endef

$(eval $(foreach t,$(targets),$(call target_expand,$t)))

code.py: $(code-files)
	cat $^ > $@
