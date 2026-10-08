# Product design

This is the intended product contract. Implementation progress and release
planning live in the [issues](https://github.com/godaniya/astronomical-clocks-wallpaper/issues)
and [milestones](https://github.com/godaniya/astronomical-clocks-wallpaper/milestones).

## Product purpose and newcomer comprehension

The central purpose of Astronomical Clock Wallpaper is to bring the Prague Orloj
experience beyond Staroměstské náměstí. It allows people captivated by Prague's
monumental astronomical clock to enjoy its visual presence and understand its
interlocking celestial mechanics away from the square on their daily personal screens.

To ensure the wallpaper remains engaging and educational rather than obscure, design
and visual decisions are guided by newcomer validation: checking whether people new to
the Orloj can appreciate the dial aesthetic and comprehend its primary indications
(the 24-hour civil hand, the Sun emblem and horizon/twilight plate, the illuminated
Moon phase sphere, and the rotating Zodiac ring).

Design guidance strictly distinguishes **product intent** from **validated evidence**:
- *Product intent* encompasses design hypotheses, educational aspirations, and
  intended user comprehension outcomes.
- *Validated evidence* requires concrete observations gathered through direct user
  comprehension testing (such as newcomer field evaluations) and verified physical-device
  behavior.
Feature proposals and visual modifications must not assert user demand, intuitive clarity,
or comprehension benefits without supporting evidence from actual user validation.

## One observing site and one instant

Prague Orloj is the visual and projection reference. A selected observing site
supplies the coordinates for astronomy and the geographic timezone for civil
time, including daylight-saving changes. Both displays use the same instant.
Changing the site updates both; changing the phone timezone does not change the
saved site or its civil clock. Before a site is selected, the civil clock uses
the phone timezone and site-dependent astronomy is hidden.

[Issue #41](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/41)
generalizes this single-dial contract into a pluggable family of astronomical
clocks; this section describes the Prague dial until that seam lands.

Adapt the Orloj geometry to the selected site's latitude and longitude, including
southern-hemisphere and polar sites. Draw original artwork. Detailed projection
mathematics belong in the Orloj guide introduced by
[PR #30](https://github.com/godaniya/astronomical-clocks-wallpaper/pull/30).

## Location selection and offline operation

Initial setup requests current location through Android's built-in location API
and accepts approximate results. Denial, disabled location, failure, or timeout
must leave offline city selection and coordinate entry available. Manual selection
is also directly available; settings allow explicit refresh or a different site.
Persist the selection without continuous background location tracking.

Every input method must establish the site's geographic timezone. Capturing the
phone timezone alone is insufficient; use a geographic IANA timezone with its
daylight-saving rules. Manual setup and runtime calculations must work offline,
without proprietary SDKs. Bundled data and artwork require recorded provenance
and licenses.

## Display scope

Support home and lit lock screens, subject to physical-device verification.
Render only while visible and restore the current instant and saved settings
after wake or recreation. Always On Display and interactive sky exploration are
outside the first release.
