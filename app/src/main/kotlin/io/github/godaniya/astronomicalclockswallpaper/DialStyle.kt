package io.github.godaniya.astronomicalclockswallpaper

/** Palette of colors for rendering the astronomical clock. */
internal data class DialPalette(
    val background: Int,
    val gold: Int,
    val mutedGold: Int,
    val rim: Int,
    val sky: Int,
    val twilight: Int,
    val night: Int,
    val hand: Int,
    val moonIlluminated: Int,
    val moonShadow: Int,
    val nightGold: Int,
    val nightText: Int,
)

/** Original Orloj-inspired palette; dimensions in the renderers are fractions of the sky radius. */
internal object DialStyle {
    // Font shaping needs ordinary-size text: subpixel textSize rounds glyph advances to zero.
    const val TEXT_UNITS = 1_000f

    // Pinned dark palette constants for backwards compatibility and tests
    const val BACKGROUND: Int = 0xFF101923.toInt()
    const val GOLD: Int = 0xFFD8B66A.toInt()
    const val MUTED_GOLD: Int = 0xFF887347.toInt()
    const val RIM: Int = 0xFF1C2C39.toInt()
    const val SKY: Int = 0xFF286078.toInt()
    const val TWILIGHT: Int = 0xFF9C6438.toInt()
    const val NIGHT: Int = 0xFF152433.toInt()
    const val HAND: Int = 0xFFF4E5B8.toInt()
    const val MOON_ILLUMINATED: Int = 0xFFE8EEF5.toInt()

    // The Moon marker rides the zodiac band, and ZodiacRenderer fills that band with NIGHT, so the
    // shadow tone must be its own colour: at NIGHT the unlit two-thirds of the disc vanished into
    // its background and only the gold rim separated a crescent from the band. This slate is 45
    // RGB units from NIGHT and at least 42 from every other entry, so the disc reads as a sphere
    // whether it is over the band (zodiac on) or the plain grid (zodiac off).
    const val MOON_SHADOW: Int = 0xFF2C3E50.toInt()

    val DARK_PALETTE =
        DialPalette(
            background = BACKGROUND,
            gold = GOLD,
            mutedGold = MUTED_GOLD,
            rim = RIM,
            sky = SKY,
            twilight = TWILIGHT,
            night = NIGHT,
            hand = HAND,
            moonIlluminated = MOON_ILLUMINATED,
            moonShadow = MOON_SHADOW,
            nightGold = GOLD,
            nightText = HAND,
        )

    // Light appearance palette: ivory, bronze, and pale blue with recognizable twilight/night regions
    const val LIGHT_BACKGROUND: Int = 0xFFF7F4EB.toInt()
    const val LIGHT_GOLD: Int = 0xFF6E4D25.toInt()
    const val LIGHT_MUTED_GOLD: Int = 0xFF96734B.toInt()
    const val LIGHT_RIM: Int = 0xFFE8E2D2.toInt()
    const val LIGHT_SKY: Int = 0xFF89B2CC.toInt()
    const val LIGHT_TWILIGHT: Int = 0xFFC88B58.toInt()
    const val LIGHT_NIGHT: Int = 0xFF2C3E50.toInt()
    const val LIGHT_HAND: Int = 0xFF4E341B.toInt()

    // LIGHT_NIGHT equals the dark MOON_SHADOW, so the dark pair cannot be reused here: the unlit
    // two-thirds of the disc would vanish into the zodiac band exactly as MOON_SHADOW's comment
    // records for the dark palette. The lit disc reuses the ivory plate tone, which stays legible
    // because the marker rides the night-filled band rather than the background. This slate is 136
    // RGB units (Euclidean) from LIGHT_NIGHT and 179 from the ivory, so the disc reads as a sphere.
    const val LIGHT_MOON_ILLUMINATED: Int = 0xFFF7F4EB.toInt()
    const val LIGHT_MOON_SHADOW: Int = 0xFF7A8CA0.toInt()

    // The zodiac ring is filled with `night`, which is dark in both palettes, so the light palette
    // cannot reuse its plate inks there: bronze #6E4D25 on #2C3E50 measured 1.44:1 and the `hand`
    // label tone 1.04:1, leaving the sign names unreadable. These two tones are chosen for that dark
    // surface instead - nightGold 5.80:1 against the band for the ring outline, dividers, sign star,
    // and the Sun and Moon markers that ride the ring, and nightText 8.92:1 for the sign names. Both
    // clear the WCAG 2.1 minimums (4.5:1 text, 3:1 graphics); DialPaletteTest pins them.
    const val LIGHT_NIGHT_GOLD: Int = 0xFFD9B87A.toInt()
    const val LIGHT_NIGHT_TEXT: Int = 0xFFF1E7CE.toInt()

    val LIGHT_PALETTE =
        DialPalette(
            background = LIGHT_BACKGROUND,
            gold = LIGHT_GOLD,
            mutedGold = LIGHT_MUTED_GOLD,
            rim = LIGHT_RIM,
            sky = LIGHT_SKY,
            twilight = LIGHT_TWILIGHT,
            night = LIGHT_NIGHT,
            hand = LIGHT_HAND,
            moonIlluminated = LIGHT_MOON_ILLUMINATED,
            moonShadow = LIGHT_MOON_SHADOW,
            nightGold = LIGHT_NIGHT_GOLD,
            nightText = LIGHT_NIGHT_TEXT,
        )

    fun paletteFor(appearance: DialAppearance, isSystemInNightMode: Boolean): DialPalette {
        val palette =
            when (appearance) {
                DialAppearance.LIGHT -> LIGHT_PALETTE
                DialAppearance.DARK -> DARK_PALETTE
                DialAppearance.SYSTEM -> if (isSystemInNightMode) DARK_PALETTE else LIGHT_PALETTE
            }
        return palette
    }
}
