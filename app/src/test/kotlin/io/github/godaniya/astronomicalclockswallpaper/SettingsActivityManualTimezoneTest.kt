package io.github.godaniya.astronomicalclockswallpaper

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowAlertDialog
import java.time.ZoneId

/** Verifies manual coordinate resolution, estimate confirmation, picker overrides, and recreation. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class SettingsActivityManualTimezoneTest {
    private val application = RuntimeEnvironment.getApplication()

    @Test
    fun typingSuggestsNearestZone() {
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            val button = activity.findViewById<Button>(R.id.select_timezone)

            enterCoordinates(activity = activity, latitude = "50.0875", longitude = "14.4206")
            assertEquals("Timezone: Europe/Prague", button.text.toString())

            enterCoordinates(activity = activity, latitude = "35.6762", longitude = "139.6503")
            assertEquals("Timezone: Asia/Tokyo", button.text.toString())
        }
    }

    @Test
    fun pickerOverridesAnchor() {
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            val button = activity.findViewById<Button>(R.id.select_timezone)

            enterCoordinates(activity = activity, latitude = "50.0875", longitude = "14.4206")
            assertEquals("Timezone: Europe/Prague", button.text.toString())

            button.performClick()
            val dialog = ShadowAlertDialog.getLatestDialog() as AlertDialog
            val targetZone = "Pacific/Honolulu"
            val index = TimeZoneLookup.AVAILABLE_ZONE_IDS.indexOf(targetZone)
            shadowOf(dialog).clickOnItem(index)
            assertEquals("Timezone: Pacific/Honolulu", button.text.toString())

            // Editing coordinates after explicit choice must NOT overwrite user's selected timezone
            enterCoordinates(activity = activity, latitude = "40.7128", longitude = "-74.0060")
            assertEquals("Timezone: Pacific/Honolulu", button.text.toString())

            activity.findViewById<Button>(R.id.save_location).performClick()
            val saved = LocationStore(application).load()
            assertNotNull(saved)
            assertEquals(ZoneId.of("Pacific/Honolulu"), saved?.zoneId)
            assertEquals(ObservingLocation.Source.MANUAL, saved?.source)
            assertTrue(activity.findViewById<TextView>(R.id.location_current).text.contains("Pacific/Honolulu"))
        }
    }

    @Test
    fun explicitZoneSurvivesRecreate() {
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            enterCoordinates(activity = activity, latitude = "50.0875", longitude = "14.4206")

            activity.findViewById<Button>(R.id.select_timezone).performClick()
            val dialog = ShadowAlertDialog.getLatestDialog() as AlertDialog
            val targetZone = "America/Chicago"
            val index = TimeZoneLookup.AVAILABLE_ZONE_IDS.indexOf(targetZone)
            shadowOf(dialog).clickOnItem(index)

            controller.recreate()
            val recreated = controller.get()
            val button = recreated.findViewById<Button>(R.id.select_timezone)
            assertEquals("Timezone: America/Chicago", button.text.toString())

            // Saving after recreation preserves the selected timezone
            recreated.findViewById<Button>(R.id.save_location).performClick()
            val saved = LocationStore(application).load()
            assertEquals(ZoneId.of("America/Chicago"), saved?.zoneId)
        }
    }

    @Test
    fun savedLocationInitializesZone() {
        LocationStore(application).save(
            ObservingLocation(
                latitude = 48.8566,
                longitude = 2.3522,
                source = ObservingLocation.Source.MANUAL,
                zoneId = ZoneId.of("Europe/Paris"),
            ),
        )
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            val button = activity.findViewById<Button>(R.id.select_timezone)
            assertEquals("Timezone: Europe/Paris", button.text.toString())

            // Entering new coordinates suggests the new location's anchor
            enterCoordinates(activity = activity, latitude = "-33.8688", longitude = "151.2093")
            assertEquals("Timezone: Australia/Sydney", button.text.toString())
        }
    }

    // A valid saved zone with no zone.tab anchor, which a migrated record can hold, must be shown
    // and highlighted rather than replaced by the alphabetically first entry.
    @Test
    fun pickerPreselectsNonAnchorZone() {
        LocationStore(application).save(
            ObservingLocation(
                latitude = 50.0875,
                longitude = 14.4206,
                source = ObservingLocation.Source.MANUAL,
                zoneId = ZoneId.of("Etc/GMT+2"),
            ),
        )
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            activity.findViewById<Button>(R.id.select_timezone).performClick()
            val dialog = ShadowAlertDialog.getLatestDialog() as AlertDialog

            val adapter = dialog.listView.adapter
            val entries = (0 until adapter.count).map { adapter.getItem(it) }
            assertEquals("Etc/GMT+2", entries[dialog.listView.checkedItemPosition])
        }
    }

    // An estimated zone is offered before it becomes the site's civil time: cancelling leaves the
    // site unsaved, and only accepting the estimate writes it.
    @Test
    fun estimateNotSavedUntilConfirmed() {
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            enterCoordinates(activity = activity, latitude = "45.5", longitude = "-120.25")
            activity.findViewById<Button>(R.id.save_location).performClick()

            val dialog = ShadowAlertDialog.getLatestDialog() as AlertDialog
            assertTrue(shadowOf(dialog).message.toString().contains("America/Boise"))
            assertNull(LocationStore(application).load())

            clickDialogButton(dialog, AlertDialog.BUTTON_NEGATIVE)
            assertNull(LocationStore(application).load())

            activity.findViewById<Button>(R.id.save_location).performClick()
            val confirmed = ShadowAlertDialog.getLatestDialog() as AlertDialog
            clickDialogButton(confirmed, AlertDialog.BUTTON_POSITIVE)

            assertEquals(ZoneId.of("America/Boise"), LocationStore(application).load()?.zoneId)
        }
    }

    // The estimate dialog's Choose… path opens the picker and must hand the picked zone to the
    // save, overriding the estimate that prompted it.
    @Test
    fun chooseFromEstimateSavesChoice() {
        Robolectric.buildActivity(SettingsActivity::class.java).use { controller ->
            val activity = controller.setup().get()
            enterCoordinates(activity = activity, latitude = "45.5", longitude = "-120.25")
            activity.findViewById<Button>(R.id.save_location).performClick()

            val estimateDialog = ShadowAlertDialog.getLatestDialog() as AlertDialog
            clickDialogButton(estimateDialog, AlertDialog.BUTTON_NEUTRAL)

            val picker = ShadowAlertDialog.getLatestDialog() as AlertDialog
            val targetZone = "Pacific/Honolulu"
            shadowOf(picker).clickOnItem(TimeZoneLookup.AVAILABLE_ZONE_IDS.indexOf(targetZone))

            assertEquals(ZoneId.of(targetZone), LocationStore(application).load()?.zoneId)
            assertTrue(activity.findViewById<TextView>(R.id.location_current).text.contains(targetZone))
        }
    }

    // A dialog dispatches its button click through a message on the main looper, so the write it
    // triggers has not happened until that looper drains.
    private fun clickDialogButton(dialog: AlertDialog, which: Int) {
        dialog.getButton(which).performClick()
        shadowOf(Looper.getMainLooper()).idle()
    }

    @SuppressLint("SetTextI18n")
    private fun enterCoordinates(activity: SettingsActivity, latitude: String, longitude: String) {
        activity.findViewById<EditText>(R.id.latitude_input).setText(latitude)
        activity.findViewById<EditText>(R.id.longitude_input).setText(longitude)
    }
}
