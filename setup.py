from setuptools import setup, find_packages

setup(
    name = "crobe",
    version = "0.1",
    python_requires = '>3.9',
    description = "Generic probe toolset",
    author = "Nicolas Pouillon",
    author_email = "nipo@ssji.net",
    license = "BSD",
    classifiers = [
        "Development Status :: 4 - Beta",
        "Programming Language :: Python",
    ],
    package_data = {
        '': ['*.bit.gz', '*.fs.gz', '*.hex'],
    },
    entry_points={
        'console_scripts': [
            'crobe = crobe.cli.console:cli',
        ],
        'setuptools.installation': [
            'eggsecutable = crobe.cli.console:cli',
        ]
    },
    packages = find_packages(),
    install_requires = ["pyelftools >= 0.23", "click >= 0.6", "ptpython", "tqdm", "pyusb", "pyserial", "decorator", "paramiko"],
    dependency_links=[
        'https://code.ssji.net/git/nipo/vhsic/snapshot/vhsic-c4430e08c1d3680606e01f42ad55bd0d67bb7f73.tar.gz#egg=vhsic-0.1',
    ],
    extras_require={
        'bsdl':  ["vhsic >= 0.1"],
    },
)
