"""
OpenScan needs has four major parts:

* Generate a DFA annotated with "messages",
* Convert that into a serialized form,
* Recover the DFA from the serialized form, and
* Plug into a driver supplied at the far end.

The SIMPLEST way to get part 1 accomplished is to declare that you define your scanner with the exiting miniscan
module, but just provide string messages instead of callable objects. It becomes a different set of semantics for
much the same machinery.

If the whole goal of serialized automatons were to save time on the start-up of an application, that would be OK.
I would rather see OpenScan operate on scanner definitions which are not wrapped up in Python code, though:
You should not be required to speak Python to define a scanner which will be used in a non-Python environment.
Besides, all that Python syntax is a bit noisy, as the MiniParse JSON example illustrates.

If de-fluffing the syntax is part of the goal, then OpenScan needs to adopt a suitable alternative.

"""