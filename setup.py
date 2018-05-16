from setuptools import setup, find_packages

setup(
    name = "crobe",
    version = "0.1",
    description = "Generic probe toolset",
    author = "Nicolas Pouillon",
    author_email = "nipo@ssji.net",
    license = "BSD",
    classifiers = [
        "Development Status :: 4 - Beta",
        "Programming Language :: Python",
    ],
    package_data = {
        '': ['*.bit.gz'],
    },
    use_2to3 = False,
    packages = find_packages(),
    install_requires = ["pyelftools >= 0.23", "vhsic >= 0.1", "click >= 0.6", "crcmod"],
    dependency_links=[
        'https://code.ssji.net/git/nipo/vhsic/snapshot/vhsic-c4430e08c1d3680606e01f42ad55bd0d67bb7f73.tar.gz#egg=vhsic-0.1',
    ],
)
