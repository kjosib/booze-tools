# Hidden Recursion
There's a stress test for dealing well with epsilon rules:
Hidden Recursion causes weak algorithms to either miss
correct sentences or diverge. 


## Productions: HiddenLeft HiddenRight HiddenMid 

NB: Mentioning all three of `HiddenLeft`, `HiddenRight`, and `HiddenMid` on the `Productions` header
marks them all three as potential start symbols for the parse table this grammar generates.

```
HiddenLeft -> a | epsilon _ b
```
Hidden left recursion causes the brute-force approach to
diverge because it cannot guess how many times it must
reduce an epsilon rule before shifting a token.

```
HiddenRight -> a _ epsilon | b
```
Hidden right recursion is fine under brute force because eventually
the parser runs out of branches to cancel, but it causes weaker GSS
implementations to reject some of the language. Unfortunately, for
the moment it appears strength costs time and complexity.

```
HiddenMid -> a | epsilon _ epsilon
```
You could argue that hidden-middle recursion is pathological:
A corresponding parse tree has every depth at once. Nevertheless,
somehow the system magically copes with it. Actually, no magic at all:
It just happens to be a recursive pun. With care, these things
have a place in language processing.

```
epsilon -> :nothing
```

## Precedence
```
%nondeterministic
```
