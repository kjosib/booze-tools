Introduction
================

Booze-Tools aims to be the ultimate Swiss-Army Knife of
language-processing tasks.  It does quite a bit so far.
and has some features not found in other such tools.
It happens to be written in Python.

Documentation Migration in Progress
--------------------------------------

At this very moment, most of what documentation there is
lives on the wiki_ page. In time, more should migrate over.


Why and Wherefore?
----------------------

Yes, there are other language tools out there, but this is a
journey and I plan to enjoy it.

The original pipe-dream was for this library to become the complete
programming-language development workbench of choice, but written
in a high-level language (not C or C++, like GCC or LLVM). Therefore,
the Booze-Tools will grow whatever additional bits make that happen.
It does not stop with lexical analysis and context-free parsing.

The next goal was to explore solutions to annoying features
of other popular language-processing subsystems. That's why,
for instance, :code:`macroparse` supports macro-expansion of context-free
production rules. (This turns out to be more expressive than EBNF.)

I wanted a single system that could *in principle* be used to generate
scanners/parsers for other host-languages than just Python.
That's why there's a JSON output format and a system of *messages*
rather than embedded code: current scripting languages can read JSON
directly, and independent tools can turn it into (for instance) C code.
By implementing a small driver, you can re-use a language definition
that was originally made for some other purpose. This feature may
keep an ecosystem of tools in sync with each other.

Another key goal is that the project source code should end up clear and
instructive. In a perfect world, you could reference this code in a
compiler-compiler course. (The world is far from perfect.) Therefore,
there are heavy comments in parts that deal in the classical algorithms
and data structures peculiar to the field of compilers. If you see
something unclear, please speak up. Opacity is a bug.

To that same end, I may eventually add on some alternative constructions,
as (perhaps) for SLR and LR(0) as ends in themselves, with heavy commentary.
At one point I was digging deep into the issues involved with ambiguous grammars,
which is why the :code:`parsing.general` submodule exists. The experience
contributed greatly to the error-recovery mechanisms in the main parsing algorithm.

Finally, it seems that many data analysis tasks are greatly simplified
if you can treat them as *parsing with a bit extra*. I want to make it
absolutely convenient to develop and deploy such intermixed applications.

.. _wiki: https://github.com/kjosib/booze-tools/wiki
