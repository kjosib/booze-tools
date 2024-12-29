Invoking the *Booze-Tools* Metacompiler
========================================

Let's say you looked at the `GitHub repository <https://github.com/kjosib/booze-tools>`_
at `the examples, <https://github.com/kjosib/booze-tools/tree/master/example>`_
and decided the concept was pretty cool. How shall we proceed?

All of the examples are coded to build their grammar into a parser at run-time.
That's alright for a demonstration, but how would you deal with this in a real project?

You could choose to copy a line of code, but actually there are a number of other handy features
available on the command-line.

Extremely Short Version
-------------------------

On the command line:

.. code-block:: text

    D:\GitHub\booze-tools>py -m boozetools example\pascal.md
    Wrote automaton in JSON format to:
            example\pascal.automaton

Then later, in Python code, something like:

.. code-block:: python

    import json
    from boozetools.macroparse import runtime

    tables = json.load('example/pascal.automaton')

    class MyParser(runtime.TypicalApplication):
        def __init__(self):
            super().__init__(tables)

        def scan_this(self, yy):
            yy.token('this', yy.match())

        def parse_that(self, left, middle, right):
            return That(left, middle, right)

    syntax_tree = MyParser().parse("some big long text")

A Bit More Detail
------------------

You have lots of options about how you invoke this:

.. code-block:: text

    D:\GitHub\booze-tools>py -m boozetools -h
    usage: py -m boozetools [-h] [-f] [-o OUTPUT] [-i] [--pretty] [--csv] [--dev] [--dot] [-m {LALR,CLR,LR1}] [-v]
                            source_path

    Compile a macroparse grammar/scanner definition from a markdown document into a set of parsing and scanning tables in
    JSON format. The resulting tables are suitable for use with the included runtime modules. Pypi:
    https://pypi.org/project/booze-tools/ GitHub: https://github.com/kjosib/booze-tools/wiki
    ReadTheDocs: https://boozetools.readthedocs.io/en/latest/

    positional arguments:
      source_path           path to input file

    optional arguments:
      -h, --help            show this help message and exit
      -f, --force           allow to write over existing file
      -o OUTPUT, --output OUTPUT
                            path to output file
      -i, --indent          indent the JSON output for easier reading.
      --pretty              Display uncompressed tables in attractive grid format on STDOUT.
      --csv                 Generate CSV versions of uncompressed tables, suitable for inspection.
      --dev                 Operate in "development mode" -- which changes from time to time.
      --dot                 Create a .dot file for visualizing the parser via the Graphviz package.
      -m {LALR,CLR,LR1}, --method {LALR,CLR,LR1}
                            Which parser table construction method to use.
      -v, --verbose         Squawk, mainly about the table compression stats.

Error Handling?
------------------

There is support for that.

Error Rules:
    You can write error production-rules using the metatoken ``$error$``.
    The machinery surrounding this takes pains to do well.
    It may not be the fastest concept, but it's smarter than the average parser.

On-Error Call-Backs:
    For everything else, there are error call-backs.
    If you look in ``boozetools/macroparse/runtime.py``
    (`here <https://github.com/kjosib/booze-tools/blob/master/boozetools/macroparse/runtime.py>`_)
    you'll find ``class TypicalApplication`` which defines default behavior for
    situations in which (a) the parser's error-rule mechanism was unable to resolve,
    or (b) a stuck scanner.

