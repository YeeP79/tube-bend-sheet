"""Resolve additive conflicts by keeping ours then theirs (both sides added lines)."""
import re, sys
for p in sys.argv[1:]:
    s = open(p).read()
    pat = re.compile(r'<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n', re.S)
    n = len(pat.findall(s))
    s = pat.sub(lambda m: m.group(1) + m.group(2), s)
    open(p, 'w').write(s)
    print(p, n, 'hunks')
