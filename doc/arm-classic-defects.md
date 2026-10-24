# ARM classic (ARM9 / ARM926EJ-S) debug: known defects

Review of `crobe/component/arm/classic/` (armv5.py, jtag.py,
debug.py, embedded_ice.py) against the ARM926EJ-S and ARM9EJ-S TRMs
and the ARM Architecture Reference Manual. Line numbers refer to
commit e230487.

Items marked *verified* were reproduced by running the code; the
others come from reading it.

## Encoding and scan chain bugs

- **CP15 scan chain has the wrong length** (jtag.py:40, *verified*).
  `CP15 = jtag.Dr(Ice._width, ...)` uses the 38-bit EmbeddedICE width,
  while chain 15 on the ARM926EJ-S is 48 bits (`Cp15` is correctly
  declared over 48 bits). The opcode fields at [47:33] are never
  shifted in, so every CP15 access through chain 15 targets the wrong
  register.

- **`mrc()` / `mcr()` can't be called** (armv5.py:263-308, *verified*).
  `Mcrc` names the ARM register field `rn` but the helpers pass
  `rd=`, so building the instruction raises `AttributeError: 'Mcrc'
  object has no attribute 'rd'`.

- **CRm field is 3 bits instead of 4** (armv5.py:272).
  `crm = bitfield.Field(0, 3)` drops bit 3, so CRm 8-15 is encoded
  as CRm 0-7. Cache maintenance (c7, CRm 10/14) and TLB operations
  are affected.

- **Immediate encoder hangs on zero** (armv5.py:61, *verified*).
  `_imm8_decompose(0)` never returns (`ctz(0)`). So
  `movi(rd, 0)` hangs, and so does `RegsWriteSlow` for any value
  whose low byte is zero.

- **`mov(rd, rm, shift)` ignores `shift`** (armv5.py:104, 92). The
  argument ends up in `reg_shift`, the register-shift *flag*, and
  `mov` doesn't even forward it. Only `shift=0` gives the expected
  encoding.

## Debug operations

- **`dcc_pop_fast` typo** (debug.py:345): `r.rata` instead of
  `r.rdata`, so it raises `AttributeError` as soon as one valid word
  is read.

- **Debug `print()` leftovers**: `asm_run` (debug.py:218) prints
  every opcode on each call. `XpsrRead.ops` (debug.py:668-672)
  prints the whole JTAG sequence each time it is lowered.

- **`XpsrWrite` installs a bogus postprocess** (debug.py:707). It
  copies the `XpsrRead` read-back plumbing: it hooks `tdo_handle` on
  a shift that isn't read, and `tdo_handle` overwrites
  `self.value`, the value being written.

- **`raise NotImplemented(...)`** (debug.py:185, 194).
  `NotImplemented` is not an exception class, so accessing a
  coprocessor other than CP15 raises `TypeError` instead of the
  intended error.

- **Watchpoint control mask construction** (debug.py:590).
  `~int(control_mask) & ~0x8` forces every control bit not
  explicitly cared about into "ignore", including bits 9-31, and
  produces a negative Python int that relies on later masking. The
  nOPC bit is always compared. A breakpoint built with
  `instruction=None` but `thumb=`/`jazelle=` set gets `data=0`, which
  is right, but a data watchpoint can't select read vs write: `write`
  is accepted but never copied to `control`.

## Context save/restore

- **Saved r0 is wrong** (debug.py:21-31). `Arm926Context.save` runs
  `XpsrRead` (`MRS r0, ...`) twice before `RegsRead`, so `r00` holds
  the SPSR instead of r0. Restore then writes that value back into
  r0.

- **SPSR is accessed in every mode**. Reading or writing SPSR in User
  or System mode is UNPREDICTABLE; `save`/`restore` do both
  unconditionally.

- **No PC correction**. `RegsRead(range(0, 16))` returns the raw r15
  captured by `STM` in debug state, which is ahead of the halt
  address by an amount that depends on how debug state was entered.
  Nothing subtracts the offset per entry reason (the TRM gives the
  offsets per entry type).

- **No Thumb or Jazelle state handling**. A core halted in Thumb
  state runs the ARM debug instruction sequences as Thumb code.
  DebugStatus.itbit/ijbit are decoded but never looked at.

- **No banked registers**. Only the current mode's r8-r14 are saved;
  FIQ/IRQ/SVC/ABT/UND banks are neither readable nor preserved.

- **Resume sequence** (debug.py:770). `ResumeAt` loads the PC with
  `LDMIA` and restarts without the pipeline-correcting branch
  OpenOCD issues on ARM9 (`B` back by the number of instructions
  executed since the PC write, at system speed). Not checked on
  hardware; worth checking that execution really starts at `pc`.

## Memory access

- **Registers clobbered**. `mem_read`/`mem_write` (debug.py:237,
  283) use r14 as base and r0-r13 as data without saving them.
  Reading memory from a debugger session therefore corrupts the
  halted program's registers.

- **Word-only, aligned-only**. `mem_write` refuses unaligned
  addresses and lengths; `mem_read` reads whole words around the
  range. There is no byte/halfword path, so MMIO with narrow
  registers can't be accessed safely.

- **No cache/MMU awareness**. Accesses go through the core with
  whatever MMU and cache configuration is live. Data written for
  code loading can stay in the D-cache, while the I-cache keeps stale
  lines. Nothing cleans/invalidates or turns the caches off.

- **No abort detection**. A data abort during a system-speed
  access is not detected (DebugStatus/the core mode are not checked
  after the access). The read returns garbage and the core is left
  in Abort mode.

## Fixed in acrobe

acrobe's ARM9 support (`acrobe/component/arm/a32.py`,
`acrobe/component/arm/arm9/`, `acrobe/target/arm/arm9.py`) was
fixes all of the above with three limits: the PC correction is one
fixed offset, not per entry reason; halting in Thumb or Jazelle
state is refused rather than handled; banked registers are not
exposed. Its system-speed memory path is not yet validated on
hardware.

## Fixed in crobe

All the defects above are fixed in `crobe/component/arm/classic/`:

- Encoders: chain 15 is 48 bits, `Mcrc` uses `rd` and a 4-bit CRm,
  `imm8_encode` searches rotations and raises `ValueError` on
  unencodable values, `mov` encodes shifts, `b` takes a word offset.
  Byte and halfword loads/stores are added.
- CP15 accesses read the chain back and poll the access-complete
  bit (`Cp15Readback`).
- Watchpoint control mask only ignores the low 8 control bits that
  are not specified, always compares nOPC, and data watchpoints
  honor `write`.
- `Debug.halt()` saves a `Context` holding all register banks and
  SPSRs (none for User/System). Registers are read before CPSR, PC
  is `r15 - PC_ENTRY_OFFSET` (24 for every ARM state entry reason,
  as the k-th debug instruction sees PC = return + 16 + 4k).
  `reg_read`/`reg_write` work on this context; `resume()` writes it
  all back, then loads PC and leaves debug state with `B -4` and a
  system-speed NOP.
- Memory accesses use r0 as base and r1-r14 as data, split in
  naturally aligned byte/halfword/word accesses, and run in System
  mode when halted in User (privilege) or Abort (detection) mode. An
  abort is detected by a CPSR mode change after each run, CPSR is
  restored and `MemoryAbort` is raised. Clobbered registers are
  restored from the context on resume.
- After memory writes, `resume()` cleans the D-cache (debug override
  test-and-clean-all), drains the write buffer and invalidates the
  I-cache. `caches_disable()` turns MMU and caches off.

Remaining limits: Thumb and Jazelle state halts are refused with
`NotImplementedError`; resume clears both watchpoints; the context
logic is covered by `tests/arm_classic` against a core model only,
not validated on hardware.
