# Astronomy documentation series

This directory documents the astronomical calculations, coordinate systems, projection geometry,
and cultural astrometry frameworks implemented in the Astronomical Clock Wallpaper.

## Series roadmap

The astronomy documentation is organized into modular specifications:

| Document | Scope and content |
| --- | --- |
| [Calculations and engine specification](calculations.md) | The Kotlin calculation engine (`AstronomyCalculator`, `AstronomyEngineCalculator`), units, atmospheric refraction fits, Hipparcos star reduction, UTC event windows, failure behavior, and independent test tolerances against JPL Horizons, USNO, and IAU SOFA fixtures. |
| [Ecliptic frames, tropical zodiac, and solar terms](ecliptic-and-solar-terms.md) | The mathematical identity between the Western tropical zodiac and Chinese 24 Solar Terms (定氣法), 12 Solar Stations (十二次), 12 Monthly Generals (月將), stereographic chirality, and Northern vs. Southern Hemisphere duality. Fulfills [#65](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/65). |

## Related specifications

- [Orloj dial foundation](../orloj.md): Detailed Prague Orloj dial geometry, astrolabe-style stereographic projection mathematics, Sun/Moon marker conventions, and WCAG palette contrast contracts.
- [Product design](../design.md): The observing-site contract anchoring both civil time and celestial mechanics to one geographic location.
- [Dependency provenance](../dependencies.md): Licenses and pinned revisions for Astronomy Engine and Hipparcos stellar data.

## Architectural horizon (v0.4 Pluggable Clock Family)

As part of the multi-dial expansion framework ([Issue #41](https://github.com/godaniya/astronomical-clocks-wallpaper/issues/41)),
future documentation in this series will expand into non-European historical clocks and coordinate systems,
including:
- Equatorial armillary spheres and the 28 Lunar Mansions (二十八宿).
- Historical temporal hour systems (unequal/seasonal hours, Roman vigils, and traditional Chinese *Ke* 刻 and *Geng-Dian* 更點 systems).
- Lunisolar calendrical mechanics and leap-month rules (置閏規則).
