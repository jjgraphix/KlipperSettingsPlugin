## KlipperSettingsPlugin

*KlipperSettings version 1.0 is now available!*<br/>
*Thank you to everyone who helped with beta testing and provided feedback.*

Plugin for Ultimaker Cura which adds a new **Klipper Settings** category with a number of Klipper-specific settings and features to the main settings list. Only compatible with [*Klipper firmware*](https://github.com/Klipper3d/klipper/). All features are designed to work without the need for additional Klipper macros.

This project is an evolution of my earlier [PressureAdvanceSettingPlugin](https://github.com/jjgraphix/PressureAdvanceSettingPlugin), which is no longer supported. The new Klipper settings category includes improved Pressure Advance settings as well as a number of additional settings and features, including calibration presets to initiate Klipper's Tuning Tower sequence.<br/>

*Compatibility tested up to Cura version 5.2.2 (SDK 8.2.0)*<br/>

### Major Release Notes - v1.0.x
- Z Offset Setting
- Z Offset Layer 0 feature
- Pressure Advance Smooth Time
- Support for 3 Tuning Tower user presets
- Pressure Advance preset calculates suggested factor value
- Firmware retraction multi-extruder support
- Firmware retraction uses Cura retraction values by default
- Various bug fixes and UI improvements
- *Experimental Features:*
  - Bed Mesh Calibrate
  - Klipper UI Preheat Support

<details><summary><em>Latest Update Notes</em></summary>
  <p><ul type="square">
    <li>Bug Fix v1.0.2</li>
      <ul type="disc">
        <li>Setting definition compatibility for older versions</li>
        <li>Fixed duplicate setting relations</li>
        <li>Fixed changing machines with preset settings enabled</li>
        <li>Smooth time not tied to pressure advance control</li>
        <li>Final warnings now combined into single message</li>
        <li>Minor fixes and setting cleanup</li>
      </ul>
  </ul></p>
</details>

<details><summary><em>Previous Release Notes (Beta)</em></summary>
  <p><ul type="square">
    <li>v0.8.0</li>
      <ul type="disc">
        <li>Compatibility for Cura version 5</li>
        <li>Adds new "Klipper Settings" category</li>
        <li>Adds Klipper velocity limit settings</li>
        <li>Pressure Advance supports per-object settings and multiple extruders</li>
        <li>Simplified Tuning Tower settings</li>
      </ul>
    <li>v0.9.0</li>
      <ul type="disc">
        <li>Adds Klipper category icon</li>
        <li>Firmware retraction settings</li>
        <li>Input shaper settings</li>
        <li>New presets feature for tuning tower:</li>
          <ul type="circle">
            <li>Pressure Advance preset</li>
            <li>Ringing Tower preset</li>
          </ul>
        <li>Improved descriptions and setting behavior</li>
        <li>Various bug fixes and improvements</li>
      </ul>
    <li>v0.9.1</li>
      <ul type="disc">
        <li>Fixed crashing in older Cura versions</li>
        <li>Custom icon now only enabled for Cura 5.0+</li>
        <li>Improved presets and backup behavior</li>
      </ul>
    <li>v0.9.2</li>
      <ul type="disc">
        <li>Fixed incorrect parameter in Pressure Advance Preset</li>
        <li>Preset layer height now suggested from nozzle size</li>
      </ul>
  </ul></p>
</details>

***Check setting visibility after updating from previous version!***

### Compatibility
**Recommended Cura Versions:** 5.0 (SDK 8.0.0) and newer.<br/>
Cura versions prior to 4.0.0 (SDK 6.0.0) are *not supported*. Versions prior to 4.5.0 may not be supported in the future and testing will be limited in versions prior to 4.8.0. Please report any issues in older versions if they're needed.

**Multiple extruders are supported for compatible settings.**

### How to Use
When first installed, the Klipper Settings category will be hidden and appears at the bottom of setting visibility preferences. It's recommended to first enable visibility of every setting then hide whatever isn't needed later. If it's not appearing, try selecting the "All" settings preset. Options such as the *Apply Suggested Settings* tuning tower feature are only visible when specific settings are active and should be left visible.

**See feature notes below and setting tool tips in Cura for information on available features.**

<details>
<summary><em>List of All Available Settings:</em></summary><br>
  <strong>Tool tips explain why some settings have negative values by default.</strong><br/><br/>

  ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/examples/KSP_AllSettings_v1.0.PNG)
</details>

*I highly recommend Ghostkeeper's [SettingsGuide](https://github.com/Ghostkeeper/SettingsGuide) Cura plugin to improve readability of tool tips.*<br/>

### Features Overview
- **Tuning Tower Calibration**</br>
  [Klipper Tuning Tower](https://www.klipper3d.org/G-Codes.html#tuning_tower) settings can be used to fine tune a wide range of Klipper commands. Presets are available to easily run common Pressure Advance and Input Shaper calibrations. The *Apply Suggested Settings* option will automatically apply additional printer settings necessary for each calibration as defined in the Klipper documentation. All changed settings are backed up and restored to their prior values when the tuning tower is disabled. Custom presets allow 3 unique profiles to be saved for frequently used settings.
  
  *Only one active extruder is supported.*
  
  <details>
  <summary><em>Example of tuning tower preset applied with suggested settings:</em></summary><br><p>
  
    ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/examples/KSP_Preset-ex1_v1.0.PNG)
  </p></details>

- **Pressure Advance**</br>
Klipper's pressure advance feature is used sharpen the appearance of corners, improve line width consistency and reduce ooze during non-extrude moves. This value can be adjusted for multiple extruders, individual line types and even different mesh objects in the same print. The *Pressure Advance* tuning tower preset can be used to fine tune these values as described in the [Klipper documentation](https://www.klipper3d.org/Pressure_Advance.html). An option to set the *Pressure Advance Smooth Time* value is also included.

- **Firmware Retraction**</br> 
Enables the use of <code>G10</code> and <code>G11</code> firmware retraction commands. The <code>[firmware_retraction]</code> section in [Klipper configuration](https://www.klipper3d.org/Config_Reference.html#firmware_retraction) must be enabled to use this feature. Cura's standard retraction settings are mirrored as the default values except <code>UNRETRACT_EXTRA_LENGTH</code> is disabled by default. Multiple extruders are supported without requiring additional macros. Settings for each extruder are applied immediately following gcode tool change commands (T0, T1, etc.).

- **Z Offset Control**</br>
  *Initial Layer Z Offset* applies <code>SET_GCODE_OFFSET Z_ADJUST=</code> only before gcode coordinates equal to the first layer height then immediately instructs Klipper to revert the command on the **next z axis change**, even if the print is stopped. For added safety, the maximum adjustment range is +/- first layer height.

  Due to the inherent risk, no permanent adjustment can be made to an existing offset. The *Override Z Offset* feature defines a <b>total z offset value</b> after the start gcode sequence with <code>SET_GCODE_OFFSET Z=</code>. This overrides any existing adjustment since the printer was restarted and ***will remain applied*** after the print has completed. Only recommended for advanced users or to ensure an existing offset is removed. If *Initial Layer Z Offset* is also applied, their affects will be combined.
  
  *Use of these settings are done at your own risk.*
  
- **Input Shaper Control**</br>
Controls input shaper settings associated with Klipper's resonance compensation. The *Ringing Tower* tuning tower preset can be used to manually tune these values as described in the [Klipper documentation](https://www.klipper3d.org/Resonance_Compensation.html).

- **Velocity Limits Control**</br> 
Allows control over Klipper's velocity and acceleration limits and are generally not necessary to adjust outside of tuning tower calibrations.

- **Experimental Features**</br>
Options listed as experimental have been tested but may be modified or removed in the future. Please read the corresponding tool tips in Cura for more information. Most new feature requests will first be tested here moving forward.<br/><br/>

## Installation
Cura installation packages will be available soon and hopefully KlipperSettings will be added as an official Cura plugin in the near future. Until then, follow the manual installation instructions below.

### Update from Previous Version
Simply delete and replace contents of KlipperSettingsPlugin folder with those from the latest release. *Make sure all files are replaced*. Any additional files in the previous version are obsolete or temporary and can safely be deleted.

If settings do not appear after updating, check setting visibility then try clearing preferences in Cura.cfg or delete the file and restart.

### Install from Source Files
If using the old **PressureAdvanceSettingPlugin**, please remove it before installing KlipperSettings.
  
- Download KlipperSettingsPlugin source [.zip file from Github](https://github.com/jjgraphix/KlipperSettingsPlugin/archive/refs/heads/main.zip).
  
- Open Cura, click *Help*, *Show Configuration Folder*, then navigate to "plugins" subfolder and unpack .zip file.

- Rename the folder to **"KlipperSettingsPlugin"**, removing any Github suffix (e.g. "-main"). 
  
- *Repeat process if there's a subfolder of the same name.*<br/><br/>

## More Info

For more information about Klipper firmware, see the official documentation at [Klipper3D.org](https://www.klipper3d.org).

*For a quicker response to questions or feedback, you can contact me directly at jjfx.contact@gmail.com.*

*If you wish to support my work, buying me a coffee on [Ko-Fi](https://ko-fi.com/jjjfx) is greatly appreciated but not necessary.*
