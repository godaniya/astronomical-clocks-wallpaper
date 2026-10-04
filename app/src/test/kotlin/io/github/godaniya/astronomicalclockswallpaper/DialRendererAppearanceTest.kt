package io.github.godaniya.astronomicalclockswallpaper

import android.graphics.Bitmap
import android.graphics.Canvas
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.LocalTime

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
}
