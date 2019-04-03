# Calculator Example
This is an example scanner/grammar for a simple desktop calculator with variable
assignment and recollection. It mainly exists to exercise and demonstrate the
precedence-parsing facility of `MacroParse`, but also shows one way a `MacroParse`
definition can be integrated into a real application.

A driver and functional application are at [calculator.py](calculator.py).
Testcases are [here](../tests/test_examples.py)

For a rather more verbose tutorial introduction to most of `MacroParse`, please
see [json.md](json.md) in this folder.

# Precedence
Unlike Bison, highest-precedence comes first. After all, that's the way you learned it in
grade school!
```
%right '^'
%left '*' '/'
%left '+' '-'
```
You can also use `%nonassoc` in the usual way, but this example does not require that.

# Productions START
The productions for this are pretty normal.
```
START -> .E           :evaluate
      | .var '=' .E   :assign
      | '?'           :help

E -> '(' .E ')'
  | .E '+' .E   :add
  | .E '-' .E   :subtract
  | .E '*' .E   :multiply
  | .E '/' .E   :divide
  | .E '^' .E   :power
  | '-' .E      :negate
  | variable    :lookup
  | number
```
## Definitions
These, and some of the patterns, are snarfed out of the JSON definition. Maybe there's room for
an include-library of common tokens and subexpressions?
```
wholeNumber     [1-9]\d*
signedInteger   -?(0|{wholeNumber})
fractionalPart  \.\d+
exponent        [Ee][-+]?\d+
```
## Patterns
Again, nothing fancy:
```
{signedInteger}{fractionalPart}?{exponent}?   :number
{alpha}{word}*                                :variable
\s+                                           :ignore_whitespace
{punct}                                       :punctuation
```
