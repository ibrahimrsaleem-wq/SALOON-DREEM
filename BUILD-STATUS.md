# Build status — SALOON DREEM 1.2.2

This is a source-recovery candidate. The prior encoded ZIP files were incomplete or corrupt, so the source tree was reconstructed from individually CRC-verified files. This does not imply every original file has been recovered.

Release acceptance requires API/business-rule tests, Python compile checks, JavaScript asset checks, a Windows API executable health test, an Electron portable EXE build, and an Android APK build. The current GitHub Actions result and artifacts are authoritative. No hosted production API, signed app-store package, publisher certificate or external payment/OTP integration is included.

Windows packaging generates a multi-resolution ICO from the official SALOON DREEM logo PNG and embeds it into the EXE metadata and the desktop window/taskbar. The Windows build checks that the icon was generated before packaging.
