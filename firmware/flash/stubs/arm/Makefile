targets = arm_soc_puppet
arm_soc_puppet-code = efm32series0g efm32series0 efm32series1 efm32series1gg nrf51 lpc11 stm32f01 mkl arm79 crc32_cm3 crc32_cm0
arm_soc_puppet-dest = ../../../../crobe/target/soc/arm_based/puppet_code.py

arm-prefix = arm-mutekh-eabi-

arm79-src = arm79.c
arm79-sections = dcc_cnc
arm79-cflags = -march=armv5te -Os -fPIC
arm79-arch = arm

crc32_cm3-src = crc32.c
crc32_cm3-sections = memory_crc32
crc32_cm3-cflags = -mcpu=cortex-m3 -mthumb -Os -fPIC
crc32_cm3-arch = arm

crc32_cm0-src = crc32.c
crc32_cm0-sections = memory_crc32
crc32_cm0-cflags = -mcpu=cortex-m0 -mthumb -Os -fPIC
crc32_cm0-arch = arm

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

all:

clean:
	rm -f $(clean-files)

define section_expand

$1-$2.bin: $1.o
	$($($1-arch)-prefix)objcopy $$< -j .text.$2 -O binary $$@

$1-$2.py: $1-$2.bin dump_code.py
	python3 dump_code.py $1 $2 $$< > $$@

$1-code-files += $1-$2.py
clean-files += $1-$2.bin
clean-files += $1-$2.py
$3 += $1.py

endef

define code_file_expand

$1.o: $$($1-src) $(MAKEFILE_LIST)
	$($($1-arch)-prefix)gcc -c -o $$@ $$< $($(1)-cflags) -std=c99 -ffunction-sections -g

clean-files += $1.o
clean-files += $1.py

$(foreach s,$($1-sections),$(call section_expand,$1,$s,$2))

$1.py: $$($1-code-files)
	echo "$1 = {}" > $$@
	cat $$^ | sort >> $$@

endef

define code_gen

$1-files :=
clean-files = $1.py

$(foreach t,$($1-code),$(call code_file_expand,$t,$1-files))

$1.py: $$($1-files)
	cat $$^ > $$@

all: $$($1-dest)

$$($1-dest): $1.py
	cp $$< $$@

endef

$(eval $(foreach n,$(targets),$(call code_gen,$n)))
