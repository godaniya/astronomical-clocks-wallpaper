package io.github.godaniya.astronomicalclockswallpaper

import android.app.Activity
import android.app.AlertDialog
import android.text.Editable
import android.text.TextWatcher
import android.widget.Button
import android.widget.EditText
import java.time.ZoneId

/** Encapsulates timezone selection controls and coordinate watchers for manual location entry. */
internal fun Activity.updateTimeZoneButtonText(zoneId: ZoneId) {
    findViewById<Button>(R.id.select_timezone)?.text =
        getString(R.string.select_timezone, zoneId.id)
}

internal fun Activity.showTimeZonePickerDialog(currentZone: ZoneId, onZoneSelected: (ZoneId) -> Unit) {
    // The list is the zones this device can resolve, plus the zone in effect even when it has no
    // anchor, so the current zone is highlighted rather than replaced by the first entry.
    val zones = TimeZoneLookup.pickerZoneIds(currentZone)
    val initialSelection = zones.indexOf(currentZone.id)
    val builder = AlertDialog.Builder(this)
    builder.setTitle(R.string.choose_timezone_title)
    builder.setSingleChoiceItems(zones.toTypedArray(), initialSelection) { dialog, which ->
        // resolveZone logs when it rejects an identifier; it cannot succeed here because the
        // entries came from resolvableZoneIds.
        TimeZoneLookup.resolveZone(id = zones[which])?.let(onZoneSelected)
        dialog.dismiss()
    }
    builder.setNegativeButton(android.R.string.cancel, null)
    builder.show()
}

internal fun setupCoordinateTimezoneWatcher(
    latitudeInput: EditText,
    longitudeInput: EditText,
    parseCoordinate: (EditText) -> Double?,
    onSuggestedZone: (ZoneId) -> Unit,
) {
    val watcher =
        object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {
                // No-op before text changed.
            }

            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                // No-op during text change.
            }

            override fun afterTextChanged(s: Editable?) {
                val lat = parseCoordinate(latitudeInput)
                val lon = parseCoordinate(longitudeInput)
                if (lat != null && lon != null && isValidCoordinatePair(latitude = lat, longitude = lon)) {
                    onSuggestedZone(TimeZoneLookup.lookup(latitude = lat, longitude = lon))
                }
            }
        }
    latitudeInput.addTextChangedListener(watcher)
    longitudeInput.addTextChangedListener(watcher)
}

internal fun isValidCoordinatePair(latitude: Double, longitude: Double): Boolean =
    ObservingLocation.isValidLatitude(latitude) && ObservingLocation.isValidLongitude(longitude)
