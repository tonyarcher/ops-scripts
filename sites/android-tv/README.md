# android-tv

ADB helpers for a Skyworth/Amlogic Google TV stick (Magicubic HY300:
`HP4703-Skyworth`). Disable junk with `pm disable-user` only. Never uninstall.
Never root.

`adb` must be on PATH. The TV needs Developer options + wireless debugging.
Default host is `ANDROID_TV_HOST` or `10.0.0.75:5555`.

```
python sites/android-tv/debloat.py list
python sites/android-tv/debloat.py measure --host 10.0.0.75
python sites/android-tv/debloat.py apply --batch factory-leftovers
python sites/android-tv/debloat.py apply --batch factory-leftovers --yes
python sites/android-tv/debloat.py undo --batch factory-leftovers --yes
python sites/android-tv/debloat.py undo-all --yes
```

Apply is dry-run until `--yes`. Each batch is at most 10 packages. Test HDMI,
YouTube, sound, and the keyboard after every batch before the next.

## Never disable

| Role | This stick |
| --- | --- |
| Inputs / Source / global keys | `com.sdt.globalkey` |
| HDMI / SoC | `com.droidlogic`, `com.android.providers.tv` |
| Remote | `com.google.android.tv.remote.service`, `com.mft.rcupair` |
| Play Services / Store | `gms`, `gsf`, `vending` |
| Location (boot loop) | `com.android.location.fused` |
| Keyboard | `*.inputmethod.*` |
| Home | `com.google.android.tvlauncher` until FLauncher is HOME |
| Projector hardware | `com.sdt.projector.observer`, `com.sdt.frontpanelledsservice` |
| YouTube / Chromecast / OTA | kept on this unit |

Skyworth extras (`smallclient`, `superservice`, `deviceinfo`, `ipcountry`) were
left enabled on purpose.

## Home screen

Google TV ads live in `com.google.android.tvrecommendations` and the Google
home package. Replacement is FLauncher (`me.efesser.flauncher`, Play Store).

1. Install FLauncher and open it once.
2. Set it as the home app.
3. Confirm HOME is FLauncher, then:

```
python sites/android-tv/debloat.py disable-launcher --i-installed-flauncher
python sites/android-tv/debloat.py disable-launcher --i-installed-flauncher --yes
```

If HOME is not FLauncher, the script refuses and will re-enable the Google
launcher if a disable already went through.

## Batches (this unit, 2026-09-02)

- `factory-leftovers` — factory tests, setup wizards, screensavers
- `ads-telemetry` — recommendation rows, ads APIs, Health/Calendar/Print, Netflix
- `unused-apps` — Assistant, TTS, Play Movies, YT Music, Sling, Play Games, TalkBack, Prime Video

Play Services may re-enable `tts` and `tvrecommendations` after reboot; apply
those batches again if they come back.

## Animations

```
python sites/android-tv/debloat.py animations --scale 0.5 --yes
```

Undo scales with `--scale 1`.

## Undo everything

```
python sites/android-tv/debloat.py undo-all --yes
```
