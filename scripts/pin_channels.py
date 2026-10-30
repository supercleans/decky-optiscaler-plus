#!/usr/bin/env python3
"""Record the newest build of each download channel, as of this plugin build.

Settings lets the user pick which OptiScaler nightly, which of cyboman's FSR 4
builds and which HelixSR release (for HLX FSR 4) installs use, from the build that was newest when the plugin was built
and every one published since. That starting point is what this writes, to
defaults/channel-baseline.json; the release workflow runs it before packaging.

    python3 scripts/pin_channels.py

GITHUB_TOKEN, when set, is sent with the API requests, so a CI runner's shared
address does not run into the anonymous rate limit.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

from optiscaler import dropin, hlx, nightly  # noqa: E402
from optiscaler.constants import (  # noqa: E402
    CHANNEL_BASELINE,
    DROPIN_RELEASES_API,
    HELIXSR_RELEASES_API,
    NIGHTLY_RELEASES_API,
)

OUT = ROOT / "defaults" / CHANNEL_BASELINE


def get(url):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    baseline = {}
    for channel, api, usable in (("nightly", NIGHTLY_RELEASES_API, nightly.usable_releases),
                                 ("dropin", DROPIN_RELEASES_API, dropin.usable_releases),
                                 ("helixsr", HELIXSR_RELEASES_API, hlx.usable_releases)):
        found = usable(get(api))
        if not found:
            print(f"  {channel}: no usable release on the API - refusing to write", file=sys.stderr)
            return 1
        newest = found[0]
        baseline[channel] = {"tag": newest["tag"], "published_at": newest["published_at"]}
        print(f"  {channel}: {newest['tag']} ({newest['published_at']})")
    OUT.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"  -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
