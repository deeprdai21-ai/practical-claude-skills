# Fact-check: Python's last two major releases

**6 claims checked: 3 verified, 3 partial.**

### 3. ⚠️ Partial

**Claim:** The release also [removed the distutils package, which had been deprecated since Python 3.8](https://peps.python.org/pep-0632/).

**Source checked:** https://peps.python.org/pep-0632/

> In Python 3.10 and 3.11, distutils will be formally marked as deprecated.

**Note:** The removal is right (the PEP says "Code that imports distutils will no longer work from Python 3.12"), but it was deprecated in Python 3.10, not 3.8.

### 4. ⚠️ Partial

**Claim:** According to the release page, [Python 3.12 runs about 25% faster than Python 3.11](https://www.python.org/downloads/release/python-3120/).

**Source checked:** https://www.python.org/downloads/release/python-3120/

> delivering an estimated 5% overall performance improvement

**Note:** The release page says about 5%, not 25%.

### 6. ⚠️ Partial

**Claim:** Its headline change: [the interpreter now runs without the GIL by default](https://docs.python.org/3/whatsnew/3.13.html).

**Source checked:** https://docs.python.org/3/whatsnew/3.13.html

> CPython now has experimental support for running in a free-threaded mode, with the global interpreter lock (GIL) disabled. … This is an experimental feature and therefore is not enabled by default.

**Note:** Overstated: running without the GIL is experimental and off by default, not the default.

### 1. ✅ Verified

**Claim:** Python 3.12 was [released on 2 October 2023](https://www.python.org/downloads/release/python-3120/?utm_source=newsletter&utm_medium=email).

**Source checked:** https://www.python.org/downloads/release/python-3120/

> Release date: Oct. 2, 2023

### 2. ✅ Verified

**Claim:** It brought [more flexible f-string parsing and even better error messages](https://www.python.org/downloads/release/python-3120/).

**Source checked:** https://www.python.org/downloads/release/python-3120/

> More flexible f-string parsing, allowing many things previously disallowed … Even more improved error messages.

### 5. ✅ Verified

**Claim:** A year later, [Python 3.13 was released on 7 October 2024](https://docs.python.org/3/whatsnew/3.13.html).

**Source checked:** https://docs.python.org/3/whatsnew/3.13.html

> Python 3.13 was released on October 7, 2024.

## Not checked: figures with no source

These sentences state a number or date but cite nothing, so there was nothing to check:

- More than half of professional developers now use Python at work.
