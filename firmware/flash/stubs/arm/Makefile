targets = efm32series0g efm32series0 efm32series1 efm32series1gg nrf51 lpc11 stm32f01 mkl
arm-prefix = arm-mutekh-eabi-

efm32series0g-src = efm32.c
efm32series0g-sections = flash_erase flash_write
efm32series0g-cflags = -mcpu=cortex-m3 -mthumb -Os -fPIC -DEFM32S0G
efm32series0g-arch = arm

efm32series0-src = efm32.c
efm32series0-sections = flash_erase flash_write
efm32series0-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC -DEFM32S0
efm32series0-arch = arm

efm32series1-src = efm32.c
efm32series1-sections = flash_erase flash_write
efm32series1-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC -DEFM32S1
efm32series1-arch = arm

efm32series1gg-src = efm32.c
efm32series1gg-sections = flash_erase flash_write
efm32series1gg-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC -DEFM32S1GG
efm32series1gg-arch = arm

stm32f01-src = stm32f01.c
stm32f01-sections = flash_erase flash_write opt_erase opt_write
stm32f01-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC -DFLASH_BASE=0x40022000
stm32f01-arch = arm

mkl-src = mkl.c
mkl-sections = flash_erase flash_write
mkl-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
mkl-arch = arm

nrf51-src = nrf51.c
nrf51-sections = flash_erase flash_write
nrf51-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
nrf51-arch = arm

lpc11-src = lpc11.c
lpc11-sections = iap_call
lpc11-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
lpc11-arch = arm

target = ../../../../crobe/target/soc/arm_based/puppet_code.py

all: $(target)

$(target): code.py
	cp $< $@

clean:
	rm -f $(clean-files)

code-files =
clean-files = code.py

define section_expand

$1-$2.bin: $1.o
	$($($1-arch)-prefix)objcopy $$< -j .text.$2 -O binary $$@

$1-$2.py: $1-$2.bin dump_code.py
	python3 dump_code.py $1 $2 $$< > $$@

$1-code-files += $1-$2.py
clean-files += $1-$2.bin
clean-files += $1-$2.py
code-files += $1.py

endef

define target_expand

$1.o: $($1-src) $(MAKEFILE_LIST)
	$($($1-arch)-prefix)gcc -c -o $$@ $$< $($(1)-cflags) -std=c99 -ffunction-sections -g

clean-files += $1.o
clean-files += $1.py

$(eval $(foreach s,$($1-sections),$(call section_expand,$1,$s)))

$1.py: $($1-code-files)
	echo "$1 = {}" > $$@
	cat $$^ | sort >> $$@

endef

$(eval $(foreach t,$(targets),$(call target_expand,$t)))

code.py: $(code-files)
	cat $^ > $@
