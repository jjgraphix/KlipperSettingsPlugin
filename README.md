## KlipperSettingsPlugin

**Klipper Settings 1.0 is now available in the [Cura Marketplace](https://marketplace.ultimaker.com/app/cura/plugins/JJGraphiX/KlipperSettingsPlugin)!**<br/>
*Thank you to everyone who helped with beta testing and provided feedback.*

Plugin for Ultimaker Cura which adds a new **Klipper Settings** category with a number of Klipper-specific settings and features to the main settings list. Only compatible with [*Klipper firmware*](https://github.com/Klipper3d/klipper/). All features are designed to work without the need for additional Klipper macros.

Klipper Settings is an evolution of my [PressureAdvanceSettingPlugin](https://github.com/jjgraphix/PressureAdvanceSettingPlugin), which is no longer supported. The new Klipper settings category includes improved Pressure Advance settings as well as a number of additional settings and features, including firmware retraction and calibration presets to initiate Klipper's Tuning Tower sequence. Most settings can be saved for indvidual material profiles using the [Material Settings Plugin](https://marketplace.ultimaker.com/app/cura/plugins/fieldofview/MaterialSettingsPlugin) by FieldOfView.

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

***Check setting visibility after updating from a previous version.***

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

### Cura Compatibility
**Recommended to use Cura 5.0 (SDK 8.0.0) and newer.**<br>
Versions prior to 4.0.0 (SDK 6.0.0) are not supported and prior to 4.5.0 may not be compatible in the future. Testing may be limited in versions before Cura 5.0 so please report any issues if they are still needed.

**Multiple extruders are supported for compatible settings.**

### How to Use
After installation the new Klipper Settings category will be hidden and appears at the bottom of setting visibility preferences. It's recommended to first enable visibility of every setting then hide whatever isn't needed later. If it's not appearing, try selecting the "All" settings preset. Options such as *Apply Suggested Settings* only appear when other settings are active and should be left visible.

**Most setting values will remain applied after the print until the printer is restarted**. Klipper config values cannot be modified by the plugin.

<details>
<summary><em>Example of Available Klipper Settings:</em></summary><br>
  <strong>Tool tips explain why some values are negative by default.</strong><br/><br/>

  ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/examples/KSP_AllSettings_v1.0.PNG)
</details>

**See tool tips in Cura for descriptions of every setting.**

*I highly recommend Ghostkeeper's [Settings Guide](https://marketplace.ultimaker.com/app/cura/plugins/Ghostkeeper/SettingsGuide2) plugin to improve tool tip readability.*<br><br>

## Feature Overview
- **Tuning Tower Calibration**<br>
  [Klipper Tuning Tower](https://www.klipper3d.org/G-Codes.html#tuning_tower) settings can be used to fine tune a wide range of Klipper commands. Presets are available to run common *Pressure Advance* and *Input Shaper* calibrations. The *Apply Suggested Settings* option will automatically apply additional printer settings necessary for the calibration as defined in the Klipper documentation. Any changes to Cura settings are backed up and restored to their prior values when the tuning tower is disabled. Custom presets allow 3 unique tuning tower profiles to be saved for frequent calibrations.
  
  <details>
  <summary><em>Example of tuning tower preset:</em></summary><br><p>
  
    ![image](https://github.com/jjgraphix/KlipperSettingsPlugin/blob/main/resources/images/examples/KSP_Preset-ex1_v1.0.PNG)
  </p></details>

- **Pressure Advance**<br>
Klipper's pressure advance is used sharpen the appearance of corners, improve line width consistency and reduce ooze during non-extrude moves. This can be adjusted for multiple extruders, individual line types and different mesh objects in the same print. The *Pressure Advance* tuning tower preset can be used to tune these values as described in the [Klipper documentation](https://www.klipper3d.org/Pressure_Advance.html). *Pressure Advance Smooth Time* can also be adjusted for each print.

- **Firmware Retraction**<br>
Enables the use of <code>G10</code> and <code>G11</code> firmware retraction gcode commands. The <code>[firmware_retraction]</code> section in [Klipper configuration](https://www.klipper3d.org/Config_Reference.html#firmware_retraction) must first be enabled to use this feature. Cura's standard retraction settings are mirrored as the default values, allowing settings to easily be stored for individual materials. Multiple extruders are supported without needing additional macros. Settings for each extruder are applied immediately following gcode tool change commands (T0, T1, etc.).

- **Z Offset Control**<br>
Due to the inherent risk, no setting will apply a permanent adjustment to an existing offset. The *Initial Layer Z Offset* feature applies <code>SET_GCODE_OFFSET Z_ADJUST=</code> before all gcode coordinates equal to the first layer height then instructs Klipper to revert the offset on the next z axis change, even if the print is stopped. For added safety, the maximum adjustment is +/- first layer height.<br>
  The *Override Z Offset* option defines a total offset value with <code>SET_GCODE_OFFSET Z=</code> after the start gcode sequence. This overrides any existing z offset adjustment and will remain applied. **Use caution when enabling these options.**

  *If both options are enabled, their effects will be combined for the first layer.*
  
- **Input Shaper Control**<br>
Controls settings associated with Klipper's resonance compensation. The *Ringing Tower* tuning tower preset can be used to manually tune these values as described in the [Klipper documentation](https://www.klipper3d.org/Resonance_Compensation.html).

- **Velocity Limits Control**<br> 
Controls the printer's [velocity and acceleration limits](https://www.klipper3d.org/Config_Reference.html#printer). Any changes will persist after the print has completed. These are generally not necessary to adjust outside of tuning tower calibrations.

- **Experimental Features**<br>
New features in development which have been tested but may be modified or removed in the future. Read corresponding tool tips in Cura for more information. Most new feature requests will first be tested here moving forward.
<br><br>

## Installation
Klipper Settings can now be installed directly from the [Cura Marketplace](https://marketplace.ultimaker.com/app/cura/plugins/JJGraphiX/KlipperSettingsPlugin).

After installing, enable visibility of all new settings in Cura preferences.

<details><summary><em> To Install/Update from Source Files:</em></summary><br>
  <p>
    - Download source <a href="https://github.com/jjgraphix/KlipperSettingsPlugin/archive/refs/heads/main.zip">.zip file from Github</a>.<br>
    - Open Cura, click <em>Help</em>, <em>Show Configuration Folder</em>, then navigate to "plugins" folder and unpack .zip file.<br>
    - Rename the unpacked folder to "KlipperSettingsPlugin", removing Github suffix (e.g. "-main").<br>
    - Restart Cura and check settings visibility in preferences.<br><br>
    <i>To update a previous version, simply replace all contents of the KlipperSettingsPlugin folder with the latest release.</i>
  </p>
</details>

## More Info

For more information about Klipper firmware, see the official documentation at [Klipper3D.org](https://www.klipper3d.org).

*For questions or feedback, you can contact me directly at jjfx.contact@gmail.com.*

*If you wish to support my work, buying me a coffee on [Ko-Fi](https://ko-fi.com/jjjfx) is greatly appreciated.*
