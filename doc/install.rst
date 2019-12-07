============
 Installing
============

Dependencies
============

Crobe depends on:

* python3,
* libjaylink,
* libftdi,
* libusb-1.0.

Most Python dependencies will be resolved by pip. If you intend to use
BSDL, you'll need to install Vhsic from
https://code.ssji.net/git/nipo/vhsic manually first.

pip
===

As most python packages, crobe may be installed through pip. But as
crobe is not referenced in PyPI, you need to checkout the repository
first::

  $ git clone https://code.ssji.net/git/nipo/crobe

Then in crobe directory::

  $ pip3 install --user -e .

* `--user` is to install it in user-specific library path rather than
  on host root filesystem,

* `-e` is to make it editable, it implies the checked-out repository
  is used in-place by installation. All modification on crobe code
  base will be usable without further reinstallation.


