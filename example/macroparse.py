"""
This module contains the example drivers for applications of the sample MacroParse grammars also found
herein. They are exercised in the testing framework.

The ideal design is still being discovered. One way or another, it's necessary to bind the messages of
a definition to a set of functions and their shared context per-parse. The way that seems most natural
in Python is to let a class definition provide the implementations.

For a parser, the job is a little easier: Messages correspond to reduction functions, so the interface
is rather unsurprising.

The hinkey bit is the interface between scanner and parser. The full generality of scanning features,
including all the usual forms of context-dependent scanning, require the individual scanner actions
to call into the parser with zero or more tokens, potentially sharing state with the parse actions.

It's anticipated that relatively few fundamentally distinct scanner actions would be required for
most applications that also involve a parser, so therefore requiring the explicit call into a
parser object is not any major inconvenience.

"""

# JSON -- Scanner:

# JSON -- Parser:

