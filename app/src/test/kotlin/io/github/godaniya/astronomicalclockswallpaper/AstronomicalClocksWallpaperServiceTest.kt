package io.github.godaniya.astronomicalclockswallpaper

import android.annotation.SuppressLint
import android.app.WallpaperInfo
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Looper
import android.service.wallpaper.WallpaperService
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.time.Duration
import java.time.Instant

/** Verifies Android discovery, binding protection, metadata, service teardown, and tick scheduling. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class AstronomicalClocksWallpaperServiceTest {
    private val controller = Robolectric.buildService(AstronomicalClocksWallpaperService::class.java)

    @Before
    fun createService() {
        controller.create()
    }

    @After
    fun destroyService() {
        controller.destroy()
    }

    // This test queries only its own package, which is always visible.
    @SuppressLint("QueryPermissionsNeeded")
    @Test
    fun wallpaperDeclaration() {
        val service = controller.get()
        val intent = Intent(WallpaperService.SERVICE_INTERFACE).setPackage(service.packageName)
        val matches = service.packageManager.queryIntentServices(intent, PackageManager.GET_META_DATA)
        assertEquals(1, matches.size)
        val info = matches.single()
        assertTrue(info.serviceInfo.exported)
        assertEquals("android.permission.BIND_WALLPAPER", info.serviceInfo.permission)
        val wallpaper = WallpaperInfo(service, info)
        assertEquals(ComponentName(service, AstronomicalClocksWallpaperService::class.java), wallpaper.component)
        assertEquals(SettingsActivity::class.java.name, wallpaper.settingsActivity)
    }

    @Test
    fun independentEngineLifecycle() {
        val service = controller.get()
        val first = service.onCreateEngine()
        val second = service.onCreateEngine()
        assertNotSame(first, second)
        first.onVisibilityChanged(false)
        first.onDestroy()
        second.onVisibilityChanged(false)
        second.onDestroy()
    }

    @Test
    fun destroyCancelsScheduledRedraw() {
        val engine = controller.get().onCreateEngine()
        val looper = shadowOf(Looper.getMainLooper())

        engine.onVisibilityChanged(true)
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)

        engine.onDestroy()
        assertEquals(Duration.ZERO, looper.nextScheduledTaskTime)
    }

    // A destroyed-then-recreated surface must resume ticking: onSurfaceDestroyed cancels the loop,
    // and only onSurfaceChanged can restart it when visibility never changes.
    @Test
    fun surfaceRecreationResumesTicks() {
        val engine = controller.get().onCreateEngine()
        val looper = shadowOf(Looper.getMainLooper())
        val holder = engine.surfaceHolder

        engine.onVisibilityChanged(true)
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)

        engine.onSurfaceDestroyed(holder)
        assertEquals(Duration.ZERO, looper.nextScheduledTaskTime)

        engine.onSurfaceChanged(holder, SURFACE_FORMAT, SURFACE_WIDTH, SURFACE_HEIGHT)
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)
    }

    @Test
    fun hiddenSurfaceStaysCancelled() {
        val engine = controller.get().onCreateEngine()
        val looper = shadowOf(Looper.getMainLooper())
        val holder = engine.surfaceHolder

        engine.onVisibilityChanged(false)
        engine.onSurfaceChanged(holder, SURFACE_FORMAT, SURFACE_WIDTH, SURFACE_HEIGHT)
        assertEquals(Duration.ZERO, looper.nextScheduledTaskTime)
    }

    // onDestroy sets isDestroyed so a late visibility callback cannot restart the tick loop on a
    // handler the service no longer owns.
    @Test
    fun postDestroyVisibilityIgnored() {
        val engine = controller.get().onCreateEngine()
        val looper = shadowOf(Looper.getMainLooper())

        engine.onDestroy()
        engine.onVisibilityChanged(true)
        assertEquals(Duration.ZERO, looper.nextScheduledTaskTime)
    }

    @Test
    fun debugBroadcastSetsOffset() {
        val service = controller.get()
        val intent =
            Intent(AstronomicalClocksWallpaperService.ACTION_DEBUG_SET_TIME).apply {
                putExtra(AstronomicalClocksWallpaperService.EXTRA_OFFSET_MINUTES, 30L)
            }
        service.handleDebugSetTime(intent)

        assertEquals(Duration.ofMinutes(30), service.debugClock.currentOffset)
    }

    @Test
    fun debugBroadcastSetsInstant() {
        val service = controller.get()
        val fixedInstant = "2026-06-21T00:00:00Z"
        val intent =
            Intent(AstronomicalClocksWallpaperService.ACTION_DEBUG_SET_TIME).apply {
                putExtra(AstronomicalClocksWallpaperService.EXTRA_INSTANT, fixedInstant)
            }
        service.handleDebugSetTime(intent)

        assertEquals(Instant.parse(fixedInstant), service.debugClock.currentFixedInstant)
    }

    @Test
    fun debugBroadcastResetsTime() {
        val service = controller.get()
        val offsetIntent =
            Intent(AstronomicalClocksWallpaperService.ACTION_DEBUG_SET_TIME).apply {
                putExtra(AstronomicalClocksWallpaperService.EXTRA_OFFSET_HOURS, 2L)
            }
        service.handleDebugSetTime(offsetIntent)
        assertEquals(Duration.ofHours(2), service.debugClock.currentOffset)

        val resetIntent =
            Intent(AstronomicalClocksWallpaperService.ACTION_DEBUG_SET_TIME).apply {
                putExtra(AstronomicalClocksWallpaperService.EXTRA_RESET, true)
            }
        service.handleDebugSetTime(resetIntent)
        assertEquals(Duration.ZERO, service.debugClock.currentOffset)
        assertNull(service.debugClock.currentFixedInstant)
    }

    private companion object {
        const val SURFACE_FORMAT = 1
        const val SURFACE_WIDTH = 200
        const val SURFACE_HEIGHT = 200
    }
}
