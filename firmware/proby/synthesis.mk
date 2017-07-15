target_part = xc6slx9tqg144-2
constraints += $(SRC_DIR)/../pinout.ucf
tool = ise

include ../../../nsl/build/build.mk

images: $(target).bit
