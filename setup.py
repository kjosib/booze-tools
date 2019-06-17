import setuptools

setuptools.setup(
	name='booze-tools',
	version='0.3.0',
	packages=['boozetools', 'boozetools.macroparse'],
	license='http://unlicense.org/',
	description='A panoply of tools for parsing and lexical analysis',
	long_description=open('README.md').read(),
	long_description_content_type="text/markdown",
	url="https://github.com/kjosib/booze-tools",
	classifiers=[
		"Programming Language :: Python :: 3",
		"License :: Public Domain",
		"Operating System :: OS Independent",
		"Topic :: Software Development :: Compilers",
    ],
)