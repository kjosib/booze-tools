# What is this?

For now there are three major components. Eventually there will be more. These are:

* MiniParse -- Provides LALR(1) and operator-precedence grammar facilities (like Lemon, YACC, or Bison).
* MiniScan -- Provides a DFA-based backtracking scanner (like Flex or Lex) with a few extra goodies.
* MacroParse -- This is the crown jewel of the package right now. It:
    * provides for a separate document containing the definitions of a scanner and parser.
    * uses markdown format to make [just such a document](https://github.com/kjosib/booze-tools/tree/master/example/json.md) into a literate program. 
    * enables a single such definition to be used for different applications on different host languages.
    * supports a macro language for simplifying otherwise-redundant parser specifications.
    * provides a suitable runtime library so the [examples](https://github.com/kjosib/booze-tools/tree/master/example/)
        run and pass the [tests](https://github.com/kjosib/booze-tools/tree/master/tests/).
    * still needs more example applications to exercise the remaining features -- which are coming soonish.

Full documentation is at [the wiki page](https://github.com/kjosib/booze-tools/wiki).
A worked example is in [/example/json.py](https://github.com/kjosib/booze-tools/tree/master/example/json.py).

The `dev` branch currently has two major focuses: proper packaging for distribution on PYPI, and improving the MacroParse module.

# Priorities?
* These operate within a Python environment.
* They have some features not found in other such tools.
* The code is deliberately kept simple, small and well-factored:
    * Easy to extend, approachable, and informative. 
    * Aiming for suitability in an instructional context.
* These modules do not generate code:
    * They plug directly into your application and work right away.
    * This makes them excellent for rapid prototyping.
    * Pickled automatons will be part of the next major feature (MacroParse).
    * Code generation for other languages is in the foreseeable future.
* Performance is accordingly NOT a top priority, but:
    * if someone wants to play with the profiler they are welcome, and
    * contributions in that vein will be accepted as long as they are consistent with the higher priorities.

# What Else?
There is a complete worked example JSON scanner/parser in the `example` folder. It has a lot of commentary to walk you through setting up both scanner and parser.

There are unit tests. They're not vast and imposing, but they exercise the interface both directly and via the example code.

There is a wiki linked above. It has background and more detail about what this is and how to use it.

