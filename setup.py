import setuptools

setuptools.setup(
	name='booze-tools',
	version='0.5.0',
	packages=[
		'boozetools',
		'boozetools.macroparse',
		'boozetools.parsing',
		'boozetools.parsing.general',
		'boozetools.scanning',
		'boozetools.support',
	],
	description='A panoply of tools for parsing, lexical analysis, and semantic processing',
	long_description=open('README.md').read(),
	long_description_content_type="text/markdown",
	url="https://github.com/kjosib/booze-tools",
	classifiers=[
		"Programming Language :: Python :: 3.9",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
		"Topic :: Software Development :: Compilers",
		"Development Status :: 4 - Beta",
    ],
)