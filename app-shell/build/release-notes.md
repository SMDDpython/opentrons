# Changes from 3.5.1 to 3.6.0

For more details, please see the full [technical change log][changelog]

[changelog]: https://github.com/Opentrons/opentrons/blob/edge/CHANGELOG.md

<!-- start:@opentrons/app -->
## Opentrons App

### Known issues

- The app's run log is still having problems displaying the current run step, especially if pauses and resumes are involved ([#2047][2047])
- The app should prevent you from starting a pipette swap while a protocol is
executing, but it does not ([#2020][2020])
- If a protocol run encounters an error, the app will suppress the error message instead of displaying it ([#1828][1828])

[2047]: https://github.com/Opentrons/opentrons/issues/2047
[2020]: https://github.com/Opentrons/opentrons/issues/2020
[1828]: https://github.com/Opentrons/opentrons/issues/1828

### Bug fixes

- Lost connection alert messages will no longer trigger when your robot is restarting for normal reasons (e.g. software update or deck calibration). Sorry for the confusion this caused!

### New features

- We've put a lot of work into improving the Wi-Fi setup experience of your robot:
    - Most 802.1X enterprise networks (e.g. eduroam) are now supported!
    - Hidden SSID networks are also supported
    - Generally, it should be easier to tell what Wi-Fi network your robot is currently connected to, along with signal strength and whether or not the network is secured
    - The robot settings page now displays the IP and MAC addresses of the Wi-Fi and Ethernet-to-USB interfaces
    - Please see our support documentation for more details
- After tip-probe is completed, the app will now move the pipette out of the way so you have better access to the deck

<!-- end:@opentrons/app -->

<!-- start:@opentrons/api -->
## OT2 and Protocol API

### Known issues

- While the underlying definition is correct, there is a known API bug that is causing the robot to think a "50ml" tube in a "15/50ml" tuberack is the same height as the "15ml" tube
- The definition of "96-well-plate" has an incorrect height. When calibrating for the first time after a factory reset:
    1. Begin labware calibration with the "96-well-plate" **off the deck**
    2. Jog the pipette up until there is enough room to insert the plate
    3. Insert plate and calibrate normally
        - After the plate has been calibrated once, the issue will not reoccur

### Bug fixes

- Fixed the iteration order of labware created with `labware.create` to match documentation
- Fixed a misconfiguration with the motor current settings for drop-tip

### New features

There aren't any new user facing features in this release, but the API team is hard at work putting exciting new stuff in place behind the scenes!

<!-- end:@opentrons/api -->
