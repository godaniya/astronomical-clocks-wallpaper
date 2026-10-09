# Product design

This is the intended product contract. Implementation progress and release
planning live in the [issues](https://github.com/godaniya/astronomical-clocks-wallpaper/issues)
and [milestones](https://github.com/godaniya/astronomical-clocks-wallpaper/milestones).

## Product purpose and newcomer comprehension

Bring the Prague Orloj experience beyond Old Town Square and onto everyday Android
screens. Visual appeal brings people in; astronomy and cultural interpretation give
them reasons to explore. The first dial is original artwork inspired by the Orloj
and adapted to the selected observing site. Learning to read it is a product
aspiration to validate, not a demonstrated comprehension benefit.

Validate aesthetic appreciation and comprehension separately: liking the dial does
not show that someone understands it, and understanding it does not show that they
find it appealing. For a lightweight newcomer evaluation, show people unfamiliar
with the Orloj a representative dial and ask what they find appealing or confusing.
Ask them to interpret the 24-hour civil hand, Sun marker and horizon/twilight plate,
Moon phase sphere, and zodiac ring before and after a brief explanation. Record the
material shown (including its source revision and depicted site/instant), prompts,
assistance, observed answers, and limitations. This defines a method, not results,
user demand, or a success threshold.

Distinguish **product intent** (design hypotheses, learning aspirations, and intended
outcomes) from **validated evidence**: observations from validation relevant to the
claim. Comprehension claims require user observations; device-behavior claims require
appropriate device verification; numerical-accuracy claims require independent
astronomical references, as described in the
[contributor verification guidance](../CONTRIBUTING.md#verification). None substitutes
for the others. Do not assert demand, intuitive clarity, or comprehension benefits
without supporting user evidence.

New feature and architecture proposals follow the existing
[product feature gate](../CONTRIBUTING.md#product-feature-gate), including its evidence
requirements. Routine documentation fixes do not expand that gate’s scope.

## Future possibilities

Other clock traditions and calendar representations could offer further ways to
explore the same sky: see the [clock-family roadmap](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/41)
and [solar-term proposal](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/66).
Configurable 節令／中氣 displays remain a future possibility, not a current capability.
Keep astronomical calculations distinct from cultural interpretations and calendar
conventions. New feature or architecture proposals must record the six product
feature gate answers before a proposal PR or implementation; existing roadmap
references do not establish approval or supporting evidence.

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
mathematics belong in the maintained [Orloj geometry guide](orloj.md).

## Location selection and offline operation

The intended contract accepts approximate current location and keeps offline city
selection and coordinate entry available after denial, disabled location, failure,
or timeout. Manual selection must also be directly available, with explicit refresh
or a different site in settings. Persist the selection without continuous background
location tracking.

Currently, settings provide approximate acquisition through Android’s built-in
network location provider and offline manual coordinate entry with a geographic
timezone selector; a city chooser is not implemented. Provider availability depends
on Android’s services and device configuration, while manual setup works offline.
A timezone selector alone supplies no coordinates. The current nearest-IANA-reference
lookup estimates a timezone rather than checking geographic boundaries, and can be
wrong near borders; review the estimate and choose the correct zone when needed.

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
