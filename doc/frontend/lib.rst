=======
Library
=======

Crobe is a python package.  Every aspect of its implementation is
available as a library and can be used programmatically.

As for the command line interface, all starts with a root::

  >>> from crobe.root import root
  >>> r = root("efm/swd")
  >>> r.start()

Starting a root triggers autodiscovery of the component tree.
Then you may query the root component for its children::

  >>> from crobe.component.arm.coresight.scs import Scs
  >>> r.children_of_class(Scs)
  [<crobe.component.arm.coresight.scs.Scs object at 0x10dddf9b0>]

The above example retrieves the objects that are a Scs.


