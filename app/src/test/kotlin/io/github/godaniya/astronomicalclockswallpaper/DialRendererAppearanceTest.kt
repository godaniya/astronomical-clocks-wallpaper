package io.github.godaniya.astronomicalclockswallpaper

import android.graphics.Bitmap
import android.graphics.Canvas
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalTime
import kotlin.math.roundToInt

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class DialRendererAppearanceTest {
    private val renderer = DialRenderer()
    private val prague = DialGeometry(localSiderealAngleDeg = 0.0, trueObliquityDeg = 23.44, latitudeDeg = 50.08)

    @Test
    fun lightRendersIvoryBackground() {
        val bitmap = Bitmap.createBitmap(400, 400, Bitmap.Config.ARGB_8888)
        renderer.renderDial(
            canvas = Canvas(bitmap),
            state = clockState(LocalTime.NOON),
            geometry = prague,
            palette = DialStyle.LIGHT_PALETTE,
        )
        val cornerPixel = bitmap.getPixel(5, 5)
        assertEquals(DialStyle.LIGHT_PALETTE.background, cornerPixel)
    }

    @Test
    fun darkRendersDarkBackground() {
        val bitmap = Bitmap.createBitmap(400, 400, Bitmap.Config.ARGB_8888)
        renderer.renderDial(
            canvas = Canvas(bitmap),
            state = clockState(LocalTime.NOON),
            geometry = prague,
            palette = DialStyle.DARK_PALETTE,
        )
        val cornerPixel = bitmap.getPixel(5, 5)
        assertEquals(DialStyle.DARK_PALETTE.background, cornerPixel)
    }

    @Test
    fun lightAndDarkDialsDiffer() {
        val lightBitmap = Bitmap.createBitmap(400, 400, Bitmap.Config.ARGB_8888)
        renderer.renderDial(
            canvas = Canvas(lightBitmap),
            state = clockState(LocalTime.NOON),
            geometry = prague,
            palette = DialStyle.LIGHT_PALETTE,
        )

        val darkBitmap = Bitmap.createBitmap(400, 400, Bitmap.Config.ARGB_8888)
        renderer.renderDial(
            canvas = Canvas(darkBitmap),
            state = clockState(LocalTime.NOON),
            geometry = prague,
            palette = DialStyle.DARK_PALETTE,
        )

        var differingPixels = 0
        for (y in 0 until 400 step 10) {
            for (x in 0 until 400 step 10) {
                if (lightBitmap.getPixel(x, y) != darkBitmap.getPixel(x, y)) {
                    differingPixels++
                }
            }
        }
        assertNotEquals(0, differingPixels)
    }

    // LIGHT_NIGHT (#2C3E50) is exactly the dark palette's MOON_SHADOW, so reusing the dark pair
    // would paint the unlit two-thirds of the disc invisibly onto the zodiac band it rides. The
    // Moon layer is the only source of LIGHT_MOON_SHADOW, so a band-only render of the same frame
    // shows whether the tone comes from the marker rather than the ring underneath it.
    @Test
    fun lightMoonShadowLeavesBand() {
        val geometry = prague.copy(moonLongitudeDeg = 60.0, moonPhaseLongitudeDeg = 90.0)
        val moonPoint = OrlojProjection(geometry).moonPoint!!
        val withMoon = render(palette = DialStyle.LIGHT_PALETTE, geometry = geometry)
        val bandOnly =
            render(
                palette = DialStyle.LIGHT_PALETTE,
                geometry = geometry,
                layers = DialLayers(isMoonEnabled = false),
            )

        val shadowPixels = countPixels(bitmap = withMoon, color = DialStyle.LIGHT_MOON_SHADOW)
        val discPixels = changedPixelsNear(first = withMoon, second = bandOnly, point = moonPoint)
        assertNotEquals(DialStyle.LIGHT_NIGHT, DialStyle.LIGHT_MOON_SHADOW)
        assertEquals(0, countPixels(bitmap = bandOnly, color = DialStyle.LIGHT_MOON_SHADOW))
        assertTrue(
            "the unlit disc must paint the light Moon shadow, found $shadowPixels pixels",
            shadowPixels > MIN_SHADOW_PIXELS,
        )
        // The disc must replace the band across its footprint, not just at one edge: under the dark
        // palette's shadow (equal to LIGHT_NIGHT) this count would collapse to the rim and sliver.
        assertTrue(
            "the disc must differ from the band over its whole footprint, found $discPixels pixels",
            discPixels > MIN_DISC_PIXELS,
        )
    }

    private fun render(
        palette: DialPalette,
        geometry: DialGeometry? = null,
        layers: DialLayers = DialLayers(),
    ): Bitmap {
        val bitmap = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888)
        renderer.renderDial(
            canvas = Canvas(bitmap),
            state = clockState(LocalTime.NOON),
            geometry = geometry,
            layers = layers,
            palette = palette,
        )
        return bitmap
    }

    private fun countPixels(bitmap: Bitmap, color: Int): Int {
        var count = 0
        for (y in 0 until bitmap.height) {
            for (x in 0 until bitmap.width) {
                if (bitmap.getPixel(x, y) == color) {
                    count++
                }
            }
        }
        return count
    }

    private fun changedPixelsNear(first: Bitmap, second: Bitmap, point: DialPoint): Int {
        val x = (CENTER + point.x * SKY_RADIUS).roundToInt()
        val y = (CENTER + point.y * SKY_RADIUS).roundToInt()
        var changed = 0
        for (dx in -PROBE_RADIUS..PROBE_RADIUS) {
            for (dy in -PROBE_RADIUS..PROBE_RADIUS) {
                if (first.getPixel(x + dx, y + dy) != second.getPixel(x + dx, y + dy)) {
                    changed++
                }
            }
        }
        return changed
    }

    private companion object {
        const val SIZE = 800
        const val CENTER = SIZE / 2.0
        const val SKY_RADIUS = SIZE * 0.43 / 1.37
        const val PROBE_RADIUS = 10
        const val MIN_SHADOW_PIXELS = 20
        const val MIN_DISC_PIXELS = 60
    }
}
