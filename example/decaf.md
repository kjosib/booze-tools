# Example `Decaf` MacroParse Specification

The [Decaf Language](https://parasol.tamu.edu/courses/decaf/students/decafOverview.pdf)
is designed for teaching a course on compilers, so it's perfect as a full-throttle example
exercise for MacroParse. Also, Decaf resembles Java, but with less caffeine.

A little poking around suggests that the definition of Decaf depends strongly on which
institution you attend. I glanced at a couple versions and I like the one linked above.
It's a bit more feature-complete than some of the other alternatives.

## Conditions



## Patterns

There are a number of keywords. They are all case-sensitive, so I can conveniently
just spell them out as patterns in the scanner. This approach will result in a larger
scan table but no need to consult a separate table of reserved words.

The plan is for reserved words to stand for themselves in the grammar definition,
so the scan action can be the same for all reserved words.

Here, I'm using the special "action" which is just a vertical bar: this means to use
the same action (and priority) as the pattern that follows on the next line.
You do need to specify a proper action before closing the code-block, though.
Otherwise, things could easily get out of hand.
```
void|int|double|bool|string|null|this     |
class|interface|extends|implements        |
for|while|if|else|return|break            |
New|NewArray|Print|ReadInteger|ReadLine   :reserved_word
```
An identifier is a sequence of letters, digits, and underscores, starting with a letter. Decaf is case-sensitive,
e.g., if is a keyword, but IF is an identifier; binky and Binky are two distinct identifiers. Identifiers can
be at most 31 characters long. A good solution is to recognize all such sequences and
deal with overlong words in the driver, but MacroParse makes it convenient to build the constraint
directly into the scanner (at the cost of a larger table).
```
{alpha}{word}{0,30}   :identifier
```

Boolean constants are also reserved. They would overlap with the definition of identifiers
(given above) but the rule priority level `:1` is higher than the default (zero) so these rules win.
```
true|false       :boolean_constant :1
```
Integer constants may be either decimal or hexadecimal using the C-style convention.
Floating point constants require a decimal point, but not necessarily a fractional part.
Strings are not allowed to span lines, and they MUST be closed. In a nod to usability,
unterminated strings are caught specifically with an extra rule here. It demonstrates
how you can add a parameter (any sequence of letters and the underscore) to an action.
```
\d+                       :decimal_integer
0[xX]{xdigit}+          :hex_integer
\d+\.\d*([eE][-+]?\d+)?   :double
"[{DOT}&&^"]*"            :string
"                         :error unterminated_string
```

Decaf uses various punctuation in its grammar. The following rules pick that up. Since we
can reasonably quote virtually anything in the production rules, all punctuation elements
(quoted) will stand for themselves.
```
{punct}  |
[<>=!]=  |
&&|\|\|  :punctuation
```
For the sake of all that is good and holy, multi-line comments will be handled in the usual
way of entering a special start condition. Single-line comments and all other whitespace are ignored.
```
\/\*            :begin IN_COMMENT
\/\/.*          |
\s+             :ignore
```

## Patterns IN_COMMENT
The idea is to scan decent-sized chunks of commentary without invoking rules too often.
It's hypothetically possible to do this as all one regex, but that would be ungainly.
```
\*+\/     :begin INITIAL
\*+/[^/]  |
[^*]+     :ignore
```

## Productions START
(This part is still under development...)
```
START -> trivial grammar
```