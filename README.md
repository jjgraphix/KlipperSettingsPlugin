## KlipperSettingsPlugin

*Compatibility tested up to Cura version 5.0.0 (SDK 8.0.0)* <br/>

Unofficial Cura plugin which adds a new "Klipper Settings" category and a number of Klipper-specific setting features to the bottom of the Cura settings list. Designed to work natively on any printer running Klipper without the need for macros.

This is a work in progress spawned from my [PressureAdvanceSettingPlugin](https://github.com/jjgraphix/PressureAdvanceSettingPlugin) which this is intended to take the place of. The current version implements the same Pressure Advance settings into the new category as well as options to initiate Klipper's Tuning Tower sequence and various other Klipper settings.

Additional features are in the works but please feel free to propose suggestions.<br/><br/>

<details><summary><em>Initial Release Notes (v0.8.0 Beta)</em></summary>
  <p><ul type="disc">
    <li>Compatible up to Cura version 5.</li>
    <li>Adds new "Klipper Settings" category</li>
    <li>Pressure Advance control with support for per-object settings and multiple extruders.</li>
    <li>Simplified Tuning Tower command settings.</li>
    <li>Klipper-specific velocity limit settings.</li>
  </ul></p>
</details>

### Current Release Notes (v0.9.0 Beta)
- Adds Klipper category icon.
- Firmware retraction settings.
- Input shaper settings.
- New preset feature for tuning tower.
  - Pressure Advance preset settings.
  - Ringing Tower preset settings.
- Improved tooltip descriptions and setting behavior.
- Various bug fixes and other improvements.

_**Check setting visibility for new features after updating!**_

### Compatibility
Tested up to Cura 5.0 but current version has not yet been extensively tested in older Cura versions. Please let me know of any issues. Multiple extruders are generally supported but new tuning tower presets may not yet properly restore setting values for all extruders. _Per-object_ Pressure Advance setting support is currently disabled for Cura versions prior to 4.7.

### How to Use

Once installed, the Klipper Settings category will initially be hidden but should show up at the bottom of the setting visibility preferences. If they don't appear, try selecting the "All" settings preset. Enable visibility of every settings to ensure it's working then hide whatever you don't plan to use. I suggest leaving visibility enabled for checkbox settings like the _Apply Suggested Settings_ preset option since they only become visible for specific settings.

<strong>Read setting tooltips for additional help with current features.</strong>

<details><summary><em>List of Supported Klipper Settings</em></summary><br>
  <strong>Read tooltips to understand why some settings can have negative values.</strong><br/><br/>
  
  ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/ksp_allsettings_0.9.0.JPG)
  
</details>
<details><summary><em>Example of Tuning Tower Settings</em></summary><br>
  <strong>Enabled checkbox stays yellow simply as a reminder the tuning tower is enabled.</strong><br/><br/>
  
  ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/ksp_ttsettings_0.9.0.JPG)
  
</details>

I highly recommend also using Ghostkeeper's amazing [SettingsGuide](https://github.com/Ghostkeeper/SettingsGuide) to improve readability of tooltips.<br/><br/>

## Installation
### If Plugin Already Installed
Simply delete and replace contents of KlipperSettingsPlugin folder with those from the latest release. *Make sure all files are replaced*. Any additional files in the previous version are obsolete or temporary and can safely be deleted. If you have issues, delete entire folder and install as instructed below.

### Install from Source Files
Uninstall **PressureAdvanceSettingPlugin**, if already added to Cura.
  
Download KlipperSettingsPlugin source [.zip file](https://github.com/jjgraphix/KlipperSettingsPlugin/archive/refs/heads/main.zip) from Github.
  
Open Cura, click *'Help'*, *'Show Configuration Folder'*, then navigate to the "plugins" subfolder and unpack .zip file there.
Rename folder to **"KlipperSettingsPlugin"**, removing suffix added by Github (e.g "-master"). 
  
*Repeat process if there's a subfolder of the same name.* <br/><br/>

## More Info

For more information about Klipper firmware, see the official documentaion at [Klipper3D.org](https://www.klipper3d.org).

*For quicker response to questions or feedback, contact me directly at jjfx.contact@gmail.com.*
