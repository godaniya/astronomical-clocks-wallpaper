package io.github.godaniya.astronomicalclockswallpaper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
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
