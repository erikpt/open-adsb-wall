"""Firmware version (issue #29). Bump this when cutting a release: the OTA
manifest's "version" (tools/gen_ota_manifest.py reads it from here) is compared
against this to decide whether an update is available, and shipping this file in
an update is what makes the device stop reporting that update afterwards."""
VERSION = "1.0.0"
