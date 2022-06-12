## KlipperSettingsPlugin

*Compatibility tested up to Cura version 5.0.0 (SDK 8.0.0)* <br><br>

Unofficial Cura plugin which adds a new "Klipper Settings" category and a number of Klipper-specific setting features to the bottom of the Cura settings list. Designed to work natively on any printer running Klipper without the need for macros.

This is a work in progress spawned from my [PressureAdvanceSettingPlugin](https://github.com/jjgraphix/PressureAdvanceSettingPlugin) which this is intended to take the place of. The current Beta version implements the same Pressure Advance settings as well as detailed options to initiate Klipper's Tuning Tower sequence and control various velocity limits.

Additional features are in the works but I'm interested to hear what you'd like to see added. Please feel free to propose suggestions above or contact me.


### Beta Release Notes (v0.8.0)
- Compatible up to Cura version 5.
- Adds new "Klipper Settings" category
- Pressure Advance control with support for per-object settings and multiple extruders.
- Simplified Tuning Tower command settings.
- Klipper-specific velocity limit settings.


#### Compatibility
Technically this is compatible with Cura 3.5.0 and newer but _Per-object_ Pressure Advance setting support is currently disabled for versions prior to 4.7. Everything else should work but has only been briefly tested in old versions. I recommend at least Cura 4.8.

### How to Use

Once installed, the Klipper Settings category will initially be hidden but should show up at the bottom of the setting visibility preferences. If they don't appear, try selecting the "All" settings preset. Enable visibility of every settings to ensure it's working then hide whatever you don't plan to use.

Read setting tooltips for additional help with current features.

<details><summary><em>Example Image of Settings</em></summary><br>
  <em>Klipper logo icon not enabled in current release.</em><br><br>
  
  ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/ksp_settings_ex1.JPG)
  
</details>

## Installation
  Uninstall **PressureAdvanceSettingPlugin**, if already added to Cura.
  
  Download KlipperSettingsPlugin source [.zip file](https://github.com/jjgraphix/KlipperSettingsPlugin/archive/refs/heads/main.zip) from Github.
  
  Open Cura, click *'Help'*, *'Show Configuration Folder'*, then navigate to the "plugins" subfolder and unpack .zip file there.
  Rename folder to **"KlipperSettingsPlugin"**, removing suffix added by Github (e.g "-master"). 
  
  *Repeat process if there's a subfolder of the same name.* <br><br/>

## More Info

For more information about Klipper firmware, see the official documentaion at [Klipper3D.org](https://www.klipper3d.org).

*For quicker response to questions or feedback, contact me directly at jjfx.contact@gmail.com.*
