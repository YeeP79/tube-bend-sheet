#!/bin/sh
# Merge a feature branch into combined file-by-file: new files copied, changed files 3-way merged
# against main; remaining conflict hunks listed for review (not auto-resolved).
set -e
b="$1"
cd ~/Projects/personal/fusion/bridge-worktrees/combined
git merge --no-commit --no-ff -q -s ours "$b"
for f in $(git diff --name-only --diff-filter=A main.."$b"); do git checkout "$b" -- "$f"; done
for f in $(git diff --name-only --diff-filter=M main.."$b"); do
  git show main:"$f" > /tmp/mb_base; git show "$b":"$f" > /tmp/mb_theirs
  if git merge-file -L combined -L main -L "$b" "$f" /tmp/mb_base /tmp/mb_theirs; then echo "clean: $f"; else echo "CONFLICT: $f"; fi
done
rm -f /tmp/mb_base /tmp/mb_theirs
