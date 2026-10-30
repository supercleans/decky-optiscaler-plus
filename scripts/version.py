#!/usr/bin/env python3
"""Decide and record the version a push to main is released as.

Used by .github/workflows/release.yml, which releases every push to main:

    python3 scripts/version.py next [--bump patch|minor|major] [--message TEXT]
        prints version=, tag=, prerelease= lines for $GITHUB_OUTPUT
    python3 scripts/version.py apply VERSION
        writes VERSION into package.json and gives it a CHANGELOG.md section

The rule for "next": package.json names the version being worked towards. If
that version has no tag yet, it is the one released - which is how a minor or
major release, or the first one, is cut: set it in package.json. Once it is
tagged, the next push bumps it: the patch number by default, or the minor or
major one when the commit subject says [minor] or [major] (or the manual run
asks for it).

The rule for "apply": the CHANGELOG's [Unreleased] section becomes this
version's, with a fresh empty [Unreleased] above it. If nothing was written
there, the section is the commit subjects since the last release instead, so a
release never goes out with no notes.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE_JSON = ROOT / "package.json"
CHANGELOG = ROOT / "CHANGELOG.md"

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")
UNRELEASED_RE = re.compile(r"^## \[Unreleased\][^\n]*\n", re.M)
LEVELS = ("patch", "minor", "major")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def package_version():
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["version"]


def bump(version, level):
    """The next version at ``level``. A prerelease's base is released first."""
    match = VERSION_RE.match(version)
    if not match:
        raise SystemExit(f"package.json version {version!r} is not MAJOR.MINOR.PATCH[-PRE]")
    major, minor, patch, pre = int(match[1]), int(match[2]), int(match[3]), match[4]
    if pre and level == "patch":
        return f"{major}.{minor}.{patch}"
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def level_from(message, requested=None):
    """The bump a commit asks for, from its subject line only."""
    if requested in LEVELS:
        return requested
    text = (message or "").splitlines()[0].lower() if message else ""
    for level in ("major", "minor"):
        if f"[{level}]" in text:
            return level
    return "patch"


def next_version(current, tags, message="", requested=None):
    """(version, bumped) for a release made from ``current``."""
    if f"v{current}" not in tags:
        return current, False
    version = bump(current, level_from(message, requested))
    # Never land on a tag that exists, however the history got there.
    while f"v{version}" in tags:
        version = bump(version, "patch")
    return version, True


def section_exists(text, version):
    return re.search(rf"^## \[?v?{re.escape(version)}\]?(\s|$)", text, re.M) is not None


def release_changelog(text, version, date, fallback_notes):
    """CHANGELOG.md with a section for ``version``."""
    if section_exists(text, version):
        return text
    match = UNRELEASED_RE.search(text)
    heading = f"## [{version}] - {date}\n"
    if match is None:
        # No [Unreleased] at all: the new section goes above the newest release.
        first = re.search(r"^## ", text, re.M)
        at = first.start() if first else len(text)
        return text[:at] + "## [Unreleased]\n\n" + heading + "\n" + fallback_notes + "\n\n" + text[at:]
    rest = text[match.end():]
    following = re.search(r"^## ", rest, re.M)
    body = rest[:following.start()] if following else rest
    head = text[:match.start()] + "## [Unreleased]\n\n" + heading
    if body.strip():
        return head + rest
    after = rest[following.start():] if following else ""
    return head + "\n" + fallback_notes + "\n\n" + after


def commit_notes():
    """Commit subjects since the last release tag, as a Markdown list."""
    tags = git("tag", "--list", "v*", "--sort=-v:refname").split()
    span = f"{tags[0]}..HEAD" if tags else "HEAD"
    subjects = [s for s in git("log", "--format=%s", "--no-merges", span).splitlines()
                if s and not s.startswith("Release v")]
    if not subjects:
        return "- Maintenance release."
    return "\n".join(f"- {subject}" for subject in subjects)


def cmd_next(args):
    tags = set(git("tag", "--list", "v*").split())
    version, bumped = next_version(package_version(), tags, args.message, args.bump)
    print(f"version={version}")
    print(f"tag=v{version}")
    print(f"prerelease={'true' if '-' in version else 'false'}")
    print(f"bumped={'true' if bumped else 'false'}")


def cmd_apply(args):
    version = args.version.lstrip("v")
    if not VERSION_RE.match(version):
        raise SystemExit(f"{version!r} is not MAJOR.MINOR.PATCH[-PRE]")
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    text, count = re.subn(r'("version"\s*:\s*")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1)
    if count != 1:
        raise SystemExit("no version in package.json")
    PACKAGE_JSON.write_text(text, encoding="utf-8")

    changelog = CHANGELOG.read_text(encoding="utf-8")
    CHANGELOG.write_text(
        release_changelog(changelog, version, datetime.date.today().isoformat(), commit_notes()),
        encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    nxt = sub.add_parser("next", help="print the version this push releases")
    nxt.add_argument("--bump", choices=LEVELS + ("",), default="")
    nxt.add_argument("--message", default="", help="the head commit's message")
    nxt.set_defaults(func=cmd_next)
    apply = sub.add_parser("apply", help="write a version into package.json and CHANGELOG.md")
    apply.add_argument("version")
    apply.set_defaults(func=cmd_apply)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
