"""Merge a feature branch's pure additions into the current file (ours).

For each block of lines the branch added relative to the base, find a unique anchor in ours
(the lines right after the block, else the lines right before) and insert the block there.
Refuses (exit 1) if the branch changed or deleted base lines, or no unique anchor exists.
Usage: additive_merge.py <base_ref> <branch_ref> <path>...
"""
import difflib, subprocess, sys

def show(ref, path):
    return subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True).stdout.splitlines(keepends=True)

def find_unique(hay, needle):
    hits = [i for i in range(len(hay) - len(needle) + 1) if hay[i:i + len(needle)] == needle]
    return hits[0] if len(hits) == 1 else None

base_ref, branch_ref, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
ok = True
for path in paths:
    base, theirs = show(base_ref, path), show(branch_ref, path)
    ours = open(path).read().splitlines(keepends=True)
    blocks = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base, theirs, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            print(f"{path}: branch modifies base lines {i1+1}-{i2}; resolve by hand"); ok = False; break
        blocks.append((i1, theirs[j1:j2]))
    else:
        for i1, block in reversed(blocks):
            pos = None
            for n in (3, 2, 1):
                after = base[i1:i1 + n]
                if after and (k := find_unique(ours, after)) is not None:
                    pos = k; break
                before = base[max(0, i1 - n):i1]
                if before and (k := find_unique(ours, before)) is not None:
                    pos = k + len(before); break
            if pos is None and i1 >= len(base):
                pos = len(ours)
            if pos is None:
                print(f"{path}: no unique anchor for block at base line {i1+1}"); ok = False; continue
            ours[pos:pos] = block
        open(path, "w").write("".join(ours))
        print(f"{path}: inserted {len(blocks)} block(s)")
sys.exit(0 if ok else 1)
