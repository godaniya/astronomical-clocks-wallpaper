package io.github.godaniya.astronomicalclockswallpaper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DialPaletteTest {
    @Test
    fun darkPaletteIsPinned() {
        assertEquals(0xFF101923.toInt(), DialStyle.DARK_PALETTE.background)
        assertEquals(0xFFD8B66A.toInt(), DialStyle.DARK_PALETTE.gold)
        assertEquals(0xFF887347.toInt(), DialStyle.DARK_PALETTE.mutedGold)
        assertEquals(0xFF1C2C39.toInt(), DialStyle.DARK_PALETTE.rim)
        assertEquals(0xFF286078.toInt(), DialStyle.DARK_PALETTE.sky)
        assertEquals(0xFF9C6438.toInt(), DialStyle.DARK_PALETTE.twilight)
        assertEquals(0xFF152433.toInt(), DialStyle.DARK_PALETTE.night)
        assertEquals(0xFFF4E5B8.toInt(), DialStyle.DARK_PALETTE.hand)
        assertEquals(0xFFE8EEF5.toInt(), DialStyle.DARK_PALETTE.moonIlluminated)
        assertEquals(0xFF2C3E50.toInt(), DialStyle.DARK_PALETTE.moonShadow)
        assertEquals(0xFFD8B66A.toInt(), DialStyle.DARK_PALETTE.nightGold)
        assertEquals(0xFFF4E5B8.toInt(), DialStyle.DARK_PALETTE.nightText)
    }

    @Test
    fun lightPaletteIsPinned() {
        assertEquals(0xFFF7F4EB.toInt(), DialStyle.LIGHT_PALETTE.background)
        assertEquals(0xFF6E4D25.toInt(), DialStyle.LIGHT_PALETTE.gold)
        assertEquals(0xFF96734B.toInt(), DialStyle.LIGHT_PALETTE.mutedGold)
        assertEquals(0xFFE8E2D2.toInt(), DialStyle.LIGHT_PALETTE.rim)
        assertEquals(0xFF89B2CC.toInt(), DialStyle.LIGHT_PALETTE.sky)
        assertEquals(0xFFC88B58.toInt(), DialStyle.LIGHT_PALETTE.twilight)
        assertEquals(0xFF2C3E50.toInt(), DialStyle.LIGHT_PALETTE.night)
        assertEquals(0xFF4E341B.toInt(), DialStyle.LIGHT_PALETTE.hand)
        assertEquals(0xFFF7F4EB.toInt(), DialStyle.LIGHT_PALETTE.moonIlluminated)
        assertEquals(0xFF7A8CA0.toInt(), DialStyle.LIGHT_PALETTE.moonShadow)
        assertEquals(0xFFD9B87A.toInt(), DialStyle.LIGHT_PALETTE.nightGold)
        assertEquals(0xFFF1E7CE.toInt(), DialStyle.LIGHT_PALETTE.nightText)
    }

    // Both palettes fill the zodiac ring with `night`, so the tones drawn on it must clear WCAG 2.1
    // against that dark surface, not against the plate. The light palette previously reused its plate
    // inks there: bronze measured 1.44:1 and the sign-name tone 1.04:1, which is the unreadable
    // zodiac names this guards.
    @Test
    fun nightBandInkStaysLegible() {
        for (palette in listOf(DialStyle.DARK_PALETTE, DialStyle.LIGHT_PALETTE)) {
            val text = contrastRatio(first = palette.nightText, second = palette.night)
            assertTrue("sign names need the 4.5:1 text minimum on the band, was $text", text >= 4.5)
            val graphics = contrastRatio(first = palette.nightGold, second = palette.night)
            assertTrue("ring ink needs the 3:1 graphics minimum on the band, was $graphics", graphics >= 3.0)
        }
    }

    private fun contrastRatio(first: Int, second: Int): Double {
        val a = relativeLuminance(first)
        val b = relativeLuminance(second)
        return (maxOf(a, b) + 0.05) / (minOf(a, b) + 0.05)
    }

    private fun relativeLuminance(color: Int): Double {
        fun channel(shift: Int): Double {
            val value = (color shr shift and 0xFF) / 255.0
            return if (value <= 0.04045) value / 12.92 else Math.pow((value + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(16) + 0.7152 * channel(8) + 0.0722 * channel(0)
    }

    // LIGHT_NIGHT equals the dark palette's MOON_SHADOW, so a light palette that copied the dark
    // pair would paint the unlit disc invisibly onto the band; the separation is the whole point.
    @Test
    fun lightMoonShadowDiffersFromBand() {
        assertNotEquals(DialStyle.LIGHT_PALETTE.night, DialStyle.LIGHT_PALETTE.moonShadow)
        assertNotEquals(DialStyle.LIGHT_PALETTE.moonIlluminated, DialStyle.LIGHT_PALETTE.moonShadow)
    }

    @Test
    fun lightRegionsAreDistinct() {
        val light = DialStyle.LIGHT_PALETTE
        assertNotEquals(light.sky, light.twilight)
        assertNotEquals(light.twilight, light.night)
        assertNotEquals(light.night, light.sky)
        assertNotEquals(light.background, light.gold)
        assertNotEquals(light.background, light.hand)
    }

    @Test
    fun paletteResolutionFollowsMode() {
        assertEquals(DialStyle.LIGHT_PALETTE, DialStyle.paletteFor(DialAppearance.LIGHT, isSystemInNightMode = true))
        assertEquals(DialStyle.LIGHT_PALETTE, DialStyle.paletteFor(DialAppearance.LIGHT, isSystemInNightMode = false))

        assertEquals(DialStyle.DARK_PALETTE, DialStyle.paletteFor(DialAppearance.DARK, isSystemInNightMode = true))
        assertEquals(DialStyle.DARK_PALETTE, DialStyle.paletteFor(DialAppearance.DARK, isSystemInNightMode = false))

        assertEquals(DialStyle.DARK_PALETTE, DialStyle.paletteFor(DialAppearance.SYSTEM, isSystemInNightMode = true))
        assertEquals(DialStyle.LIGHT_PALETTE, DialStyle.paletteFor(DialAppearance.SYSTEM, isSystemInNightMode = false))
    }
}
