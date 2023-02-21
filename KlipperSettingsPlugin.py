# KlipperSettingsPlugin v1.0.2
# Copyright (c) 2023 J.Jarrard / JJFX
# The KlipperSettingsPlugin is released under the terms of the AGPLv3 or higher.
#
# ** CREDIT **
# Special thanks to Aldo Hoeben / fieldOfView whose previous work made this possible.
# Thanks to everyone who has provided feedback and helped test the beta.

'''
KLIPPER SETTINGS PLUGIN
-----------------------
Compatible only with Klipper firmware.
Creates new 'Klipper Settings' category at the bottom of Cura settings list.
Designed to work without the need for additional Klipper macros.
Multiple extruders are supported for compatible settings.

Ultimaker Cura compatibility tested up to version 5.2.2:
Recommended Version: 5.0.0 (SDK 8.0.0) and newer.
Minimum Supported Version: 4.0.0 (SDK 6.0.0)

-------------------------------------------------
Version | Release Notes & Features
-------------------------------------------------
v0.8.0  + Tested up to Cura version 5.0
        | Pressure Advance Settings (v1.5)
        | Tuning Tower Settings
        | Velocity Limits Settings
v0.8.1  + Fixed custom category icon
v0.9.0  + Firmware Retraction Settings
        | Input Shaper Settings
        | Tuning Tower Presets feature
        | Tuning Tower Suggested Settings feature
        | Tuning Tower Preset: Pressure Advance
        | Tuning Tower Preset: Ringing Tower
v0.9.1  + Fixed crashing in older Cura versions
        | Custom icon now only enabled for Cura 5.0+
        | Improved preset and backup behavior
v0.9.2  + P.A. Preset: Fixed incorrect parameter
        | Preset layer height suggested from nozzle size
--------|
v1.0.0  + Support for 3 Tuning Tower User Presets
        | Pressure Advance Smooth Time
        | Z Offset Control
        | Z Offset Layer 0 feature
        | P.A. Preset: Suggested factor set automatically
        | Improved UI behavior
        | Experimental Features:
        | - Bed Mesh Calibrate
        | - Klipper UI Preheat Support
v1.0.1  + Firmware retraction multi-extruder support
        | Firmware retraction uses cura values by default
        | Various bug fixes
v1.0.2  + Setting definition compatibility for older versions
        | Fixed duplicate setting relations
        | Fixed changing machines with preset settings enabled
        | Smooth time not tied to pressure advance control
        | Final warnings combined into a single message
        | Setting definition cleanup

'''

import os.path, json, re
import configparser # To parse settings backup in config file
from collections import OrderedDict # Ensure order of settings in all Cura versions
from typing import List, Optional, Any, Dict, Set, TYPE_CHECKING

try:
    from PyQt6.QtCore import QUrl # Import custom images
except ImportError: # Older cura versions
    from PyQt5.QtCore import QUrl

from cura.CuraApplication import CuraApplication

from UM.Qt.Bindings.Theme import Theme # Update theme with path to custom icon

from UM.Extension import Extension
from UM.Logger import Logger # Debug logging
from UM.Version import Version # Some features not supported in older versions
from UM.Resources import Resources # Add local path to plugin resources

from UM.Settings.SettingDefinition import SettingDefinition    # Create and register setting definitions
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry

from UM.Message import Message # Display messages to user
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator # Get per-object settings

from UM.i18n import i18nCatalog # Translations
catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from UM.OutputDevice.OutputDevice import OutputDevice

class KlipperSettingsPlugin(Extension):
    def __init__(self, parent=None) -> None:
        super().__init__()

        Resources.addSearchPath(os.path.join(os.path.dirname(__file__), "resources")) # Plugin resource path

        self._application = CuraApplication.getInstance()
        self._cura_version = Version(self._application.getVersion())
        self._i18n_catalog = None  # type: Optional[i18nCatalog]
        self._global_container_stack = None # type: Optional[ContainerStack]

        self.comment = ";KlipperSettingsPlugin" # Plugin signature added to all new gcode commands

        self._settings_dict = {}   # type: Dict[str, Any]
        category_icon = self._updateCategoryIcon("Klipper") # Get supported category icon

        self._category_key = "klipper_settings"
        self._category_dict = {
            "label": "Klipper Settings",
            "description": "Features and Settings Specific to Klipper Firmware",
            "type": "category",
            "icon": "%s" % category_icon
        }
        ## Message box
        self._active_msg_list = []  # type: List[str]
        self._warning_msg = []  # type: List[str]
        self._previous_msg = None
        ## Tuning tower
        self._user_settings = {}    # type: Dict[str, Any]
        self._current_preset = None
        self._override_on = False
        # Support for 3 custom presets
        self._custom_presets = {}   # type: Dict[(int, str), Any]

        # Current firmware retraction values
        self._firmware_retract = {} # type: Dict[str, float]

        try: # Get setting definitions from json
            with open(os.path.join(os.path.dirname(__file__), "klipper_settings.def.json"), encoding = "utf-8") as f:
                self._settings_dict = json.load(f, object_pairs_hook = OrderedDict)
        except:
            Logger.logException('e', "Could not load klipper settings definition")
            return
        else: # Modify definitions for older Cura compatibility
            if self._cura_version < Version("4.7.0"):
                self._fixSettingsCompatibility()

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)
        self._application.initializationFinished.connect(self._onInitialization)

    def _onInitialization(self) -> None:
        ## Connect signals
        self._application.getPreferences().preferenceChanged.connect(self._fixCategoryVisibility)
        self._application.getMachineManager().globalContainerChanged.connect(self._onGlobalContainerChanged)
        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)
        ## Startup actions
        # Checks user settings backup in Cura config
        self._user_settings = self._getBackup() # type: Dict[str, Any]
        self._fixCategoryVisibility() # Ensure visibility of new settings category
        self._onGlobalContainerChanged() # Connect to Cura setting changes 
        self._setTuningTowerPreset() # Set status of tuning tower settings
        # Defines custom preset profiles
        for profile_nr in [1, 2, 3]:
            # Checks for preset backup in Cura config
            self._custom_presets.update(self._getBackup("preset%s" % profile_nr))

    def _onContainerLoadComplete(self, container_id: str) -> None:
        """Checks loaded containers for active definition containers.

        Registers new Klipper Settings category and setting definitions.
        """
        if not ContainerRegistry.getInstance().isLoaded(container_id):
            return # Skip containers that could not be loaded
        try:
            container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        except IndexError:
            return # Sanity check
        if not isinstance(container, DefinitionContainer) or container.getMetaDataEntry('type') == "extruder":
            return # Skip non-definition and extruder containers

        # Create new settings category
        klipper_category = SettingDefinition(self._category_key, container, None, self._i18n_catalog)
        klipper_category.deserialize(self._category_dict)
        container.addDefinition(klipper_category) # Register category setting definition

        try: # Make sure new category actually exists
            klipper_category = container.findDefinitions(key=self._category_key)[0]
        except IndexError:
            Logger.log('e', "Could not find settings category: '%s'", self._category_key)
            return

        # Adds all setting definitions to new category
        for setting_key in self._settings_dict:
            setting_definition = SettingDefinition(setting_key, container, klipper_category, self._i18n_catalog)
            setting_definition.deserialize(self._settings_dict[setting_key])
            ## Restricted: Appends new setting to the existing category definition.
            ## No existing commands are affected in the new restricted list and simply updating the
            ## definition container cache/relations seems safe in relevant Cura versions.
            klipper_category._children.append(setting_definition)
            container._definition_cache[setting_key] = setting_definition
            if setting_definition.children:
                self._updateAddedChildren(container, setting_definition)

        container._updateRelations(klipper_category) # Update relations for all category settings

    def _updateAddedChildren(self, container: DefinitionContainer, setting_definition: SettingDefinition) -> None:
        # Updates definition cache for all setting definition children
        for child in setting_definition.children:
            container._definition_cache[child.key] = child

            if child.children:
                self._updateAddedChildren(container, child)

    def _updateCategoryIcon(self, icon_name: str) -> str:
        """Returns string of compatible category icon to update Cura theme.

        Updates default Cura theme with custom icon for new settings category.
        In Cura versions before 5.0 a default icon name is returned.
         * icon_name: String for name of icon image resource without extension.
        """
        category_icon = "plugin" # Existing Cura icon if new icon fails to load

        if self._cura_version < Version("5.0.0"):
            Logger.log('d', "Category icon not compatible with Cura version %s", self._cura_version)
        else:
            try:
                icon_path = Resources.getPath(6, "%s.svg" % icon_name) # Resource type 6 (images)
            except FileNotFoundError:
                Logger.log('w', "Category icon image could not be found.")
            else:
                current_theme = Theme.getInstance()
                category_icon = icon_name
                ## Restricted: Adds new custom icon to the default theme icon dict.
                ## The only alternative found is to load an entire cloned theme with the icon.
                if icon_name not in current_theme._icons['default']:
                    current_theme._icons['default'][icon_name] = QUrl.fromLocalFile(icon_path)

        return category_icon

    def _fixSettingsCompatibility(self) -> None:
        """Update setting definitions for older Cura version compatibility.

        Prior to 4.7.0 'support_meshes_present' did not exist and tree supports was an experimental option.
        """
        pa_support = self._settings_dict['klipper_pressure_advance_factor'].get('children')['klipper_pressure_advance_support']
        pa_support_infill = pa_support.get('children')['klipper_pressure_advance_support_infill']
        pa_support_interface = pa_support.get('children')['klipper_pressure_advance_support_interface']

        for definition in [pa_support, pa_support_infill, pa_support_interface]:
            definition['enabled'] = str(definition['enabled']).replace("support_meshes_present", "support_tree_enable")

        # Updates support setting definition
        self._settings_dict['klipper_pressure_advance_factor'].get('children').update({'klipper_pressure_advance_support': pa_support})
        # Updates setting children
        self._settings_dict['klipper_pressure_advance_factor'].get('children')['klipper_pressure_advance_support'].get('children').update({
                            'klipper_pressure_advance_support_infill': pa_support_infill,
                            'klipper_pressure_advance_support_interface': pa_support_interface})

    def _fixCategoryVisibility(self, preference: str = "general/visible_settings") -> None:
        """Ensure new category is visible at start and when visibility changes.

        """
        if preference != "general/visible_settings":
            return

        preferences = self._application.getPreferences()
        visible_settings = preferences.getValue(preference)

        if not visible_settings:
            return # Empty list fixed once user adds a visible setting
        if self._category_key not in visible_settings:
            visible_settings += ";%s" % self._category_key

            preferences.setValue(preference, visible_settings) # Category added to visible settings

    def _onGlobalContainerChanged(self) -> None:
        """The active machine global container stack has changed.

        Signals when a property changes in global or extruder stacks.
        Restores user settings if the active machine changed with preset override enabled.
        """
        if self._global_container_stack: # Disconnect inactive container
            self._global_container_stack.propertyChanged.disconnect(self._onGlobalSettingChanged)
            for extruder in self._global_container_stack.extruderList:
                extruder.propertyChanged.disconnect(self._onExtruderSettingChanged)

            if self._user_settings: # Restore user settings when switching machines
                try: # Get new machine ID
                    new_active_machine_id = self._application.getMachineManager().activeMachine.getId()
                except AttributeError:
                    Logger.log('w', "Could not get active machine ID.")
                else: # Switch to previous machine because global container already changed
                    self._application.getMachineManager().setActiveMachine(self._global_container_stack.getId())
                    self._restoreUserSettings(announce = False)
                    # Sets the new active machine
                    self._application.getMachineManager().setActiveMachine(new_active_machine_id)

            self._current_preset = None
            self._setTuningTowerPreset() # Set tuning tower status

        self._global_container_stack = self._application.getMachineManager().activeMachine

        if self._global_container_stack: # Connect active container stack
            self._global_container_stack.propertyChanged.connect(self._onGlobalSettingChanged)
            for extruder in self._global_container_stack.extruderList:
                extruder.propertyChanged.connect(self._onExtruderSettingChanged)

    def _onGlobalSettingChanged(self, setting: str, property: str) -> None:
        """Setting in the global container stack has changed.

        Monitors when klipper settings in the global stack have new values.
         * setting: String of the setting key that changed.
         * property: String of the setting property that changed.
        """
        if setting.startswith("klipper") and property in ["value", "enabled"]:
            if setting.startswith("klipper_tuning"):
                self._setTuningTowerPreset() # Update tuning tower presets

    def _onExtruderSettingChanged(self, setting: str, property: str) -> None:
        """Setting in an extruder container stack has changed.

        Monitors when certain klipper settings in the active extruder stack have new values.
        Klipper retraction settings mimic Cura values until user changes are detected.
         * setting: String of the setting key that changed.
         * property: String of the setting property that changed.
        """
        if setting.startswith("klipper") and property in ["value", "enabled"]:
            is_user_value = self.settingWizard(setting, "Get hasUserValue")

            if setting.startswith("klipper_retract"):
                if setting == "klipper_retraction_speed" and is_user_value:
                    retraction_speed = self.settingWizard("klipper_retraction_speed")

                    for child in ["klipper_retract_speed", "klipper_retract_prime_speed"]:
                        values_match = (self._firmware_retract.get(setting, None) == self._firmware_retract.get(child, None))
                        value_changed = self.settingWizard(child, "Get hasUserValue")
                        # Ensures children tied to cura values follow user changes to parent setting
                        # TODO: Minor bug if parent value is set to default value again;
                        # Stop-gap until solution is found for changing the 'value' function of existing settings.
                        if not value_changed or values_match:
                            self.settingWizard(child, retraction_speed, "Set")

                # Saves previously set values to compare changes
                self._firmware_retract[setting] = self.settingWizard(setting)


    def _forceErrorCheck(self, setting_key: str=None) -> None:
        """Force error check on current setting values.

        Ensures user can't slice if Cura doesn't recognize default value as error.
        May not be necessary for all Cura versions but best to play it safe.
        All tuning tower settings checked if no setting_key specified.
         + setting_key: String for specific setting to check.
        """
        error_checker = self._application.getMachineErrorChecker()

        if setting_key:
            error_checker.startErrorCheckPropertyChanged(setting_key, "value")
        else:
            for setting in self.__tuning_tower_setting_key.values():
                error_checker.startErrorCheckPropertyChanged(setting, "value")


    def _filterGcode(self, output_device: "OutputDevice") -> None:
        """Inserts command strings for enabled Klipper settings into final gcode.

        Cura gcode is post-processed at the time of saving a new sliced file.
        """
        scene = self._application.getController().getScene()
        global_stack = self._application.getGlobalContainerStack()
        extruder_manager = self._application.getExtruderManager()
        used_extruder_stacks = extruder_manager.getUsedExtruderStacks()

        if not global_stack or not used_extruder_stacks:
            return

        # Extruders currently affected by klipper settings
        active_extruder_list = set() # type: Set[int]
        # Mesh features for pressure advance
        active_mesh_features = set() # type: Set[str]

        cura_start_gcode = global_stack.getProperty('machine_start_gcode', 'value') # To search for existing commands

        # Gets global state of klipper setting controls (bool)
        firmware_retract_enabled = global_stack.getProperty('machine_firmware_retract', 'value')
        pressure_advance_enabled = global_stack.getProperty('klipper_pressure_advance_enable', 'value')
        velocity_limits_enabled = global_stack.getProperty('klipper_velocity_limits_enable', 'value')
        input_shaper_enabled = global_stack.getProperty('klipper_input_shaper_enable', 'value')
        tuning_tower_enabled = global_stack.getProperty('klipper_tuning_tower_enable', 'value')
        smooth_time_enabled = global_stack.getProperty('klipper_smooth_time_enable', 'value')
        z_offset_enabled = global_stack.getProperty('klipper_z_offset_control_enable', 'value')
        # Experimental features
        experimental_features_enabled = global_stack.getProperty('klipper_experimental_enable', 'value')
        mesh_calibrate_enabled = global_stack.getProperty('klipper_mesh_calibrate_enable', 'value')
        ui_temp_support_enabled = global_stack.getProperty('klipper_ui_temp_support_enable', 'value')

        gcode_dict = getattr(scene, 'gcode_dict', {})
        if not gcode_dict:
            Logger.log('w', "Scene has no gcode to process")
            return

        gcode_changed = False

        new_gcode_commands = "" # String container for all new commands

        for plate_id in gcode_dict:
            gcode_list = gcode_dict[plate_id]
            if len(gcode_list) < 2:
                Logger.log('w', "Plate %s does not contain any layers", plate_id)
                continue
            if ";KLIPPERSETTINGSPROCESSED\n" in gcode_list[0]: # Only process new files
                Logger.log('d', "Plate %s has already been processed", plate_id)
                continue

            # Searches start gcode for tool change command
            # Compatibility for cura versions without getInitialExtruder
            initial_toolchange = re.search(r"(?m)^T([0-9])+$", gcode_list[1])

            if initial_toolchange: # Set initial extruder number
                start_extruder_nr = int(initial_toolchange.group(1))
            else: # Set active extruder number
                start_extruder_nr = int(self.settingWizard('extruder_nr'))

            start_extruder_stack = extruder_manager.getExtruderStack(start_extruder_nr)

            ## EXPERIMENTAL FEATURES --------------------------------
            if not experimental_features_enabled:
                Logger.log('d', "Klipper Experimental Features Disabled")
            else:
                ## BED MESH CALIBRATE COMMAND
                if not mesh_calibrate_enabled:
                    Logger.log('d', "Klipper Bed Mesh Calibration is Disabled")
                else:
                    # Search start gcode for existing command
                    mesh_calibrate_exists = self.gcodeSearch(cura_start_gcode, 'BED_MESH_CALIBRATE')

                    if mesh_calibrate_exists: # Do not add commands
                        self.showMessage(
                            "<i>Calibration command is already active in Cura start gcode.</i>",
                            "WARNING", "Bed Mesh Calibrate Not Applied", stack_msg = True)

                    else: # Add mesh calibration command sequence to gcode
                        preheat_bed_temp = global_stack.getProperty("material_bed_temperature_layer_0", 'value')
                        gcode_list[1] = "M190 S%s %s\n" % (preheat_bed_temp, self.comment) + (
                                        "G28 %s\n" % self.comment) + (
                                        "BED_MESH_CALIBRATE %s\n\n" % self.comment) + gcode_list[1]
                        gcode_changed = True

                        self.showMessage(
                            "<i>Calibration will heat bed then run before the start gcode sequence.</i>",
                            "NEUTRAL", "Klipper Bed Mesh Calibration Enabled")

                ## KLIPPER UI SUPPORT
                if not ui_temp_support_enabled:
                    Logger.log('d', "Klipper UI Temp Support is Disabled")
                else:
                    # Checks if M190 and M109 commands exist in start gcode
                    new_gcode_commands += self._gcodeUiSupport(gcode_list[1])

            ## FIRMWARE RETRACTION COMMAND --------------------------
            if not firmware_retract_enabled:
                Logger.log('d', "Klipper Firmware Retraction is Disabled")
                extruder_fw_retraction = None
            else:
                initial_retraction_settings = {}   # type: Dict[str, float]
                extruder_fw_retraction = {}  # type: Dict[int, Dict[str, float]]

                if len(used_extruder_stacks) > 1: # Add empty dict for each extruder
                    for extruder_nr in range(len(used_extruder_stacks)):
                        extruder_fw_retraction[extruder_nr] = {} # type: Dict[str, float]

                for klipper_cmd, setting in self.__firmware_retraction_setting_key.items():
                    # Gets initial retraction settings for the print
                    initial_retraction_settings[klipper_cmd] = start_extruder_stack.getProperty(setting, 'value')

                    if extruder_fw_retraction:
                        for extruder in used_extruder_stacks:
                            extruder_nr = int(extruder.getProperty('extruder_nr', 'value'))
                            # Gets settings for each extruder and updates active extruders
                            extruder_fw_retraction[extruder_nr].update({klipper_cmd: extruder.getProperty(setting, 'value')})
                            active_extruder_list.add(extruder_nr) # type: Set[int]

                for extruder_nr, settings in extruder_fw_retraction.items(): # Create gcode command for each extruder
                    extruder_fw_retraction[extruder_nr] = self._gcodeFirmwareRetraction(settings) + self.comment # type: Dict[int, str]

                try: # Add enabled commands for initial extruder to start gcode
                    new_gcode_commands += (self._gcodeFirmwareRetraction(initial_retraction_settings) + self.comment + "\n")

                except TypeError:
                    Logger.log('d', "Klipper initial firmware retraction was not set.")

            ## VELOCITY LIMITS COMMAND ------------------------------
            if not velocity_limits_enabled:
                Logger.log('d', "Klipper Velocity Limit Control is Disabled")
            else:
                velocity_limits = {} # type: Dict[str, int]
                # Get all velocity setting values
                for limit_key, limit_setting in self.__velocity_limit_setting_key.items():
                    velocity_limits[limit_key] = global_stack.getProperty(limit_setting, 'value')
                try: # Add enabled commands to gcode
                    new_gcode_commands += (self._gcodeVelocityLimits(velocity_limits) + self.comment + "\n")

                except TypeError:
                    Logger.log('d', "Klipper velocity limits were not set.")

            ## INPUT SHAPER COMMAND ---------------------------------
            if not input_shaper_enabled:
                Logger.log('d', "Klipper Input Shaper Control is Disabled")
            else:
                shaper_settings = {} # type: Dict[str, Any]
                # Get all input shaper setting values
                for shaper_key, shaper_setting in self.__input_shaper_setting_key.items():
                    shaper_settings[shaper_key] = global_stack.getProperty(shaper_setting, 'value')
                try: # Add enabled commands to gcode
                    new_gcode_commands += (self._gcodeInputShaper(shaper_settings) + self.comment + "\n")

                except TypeError:
                    Logger.log('d', "Klipper input shaper settings were not set.")

            ## TUNING TOWER COMMAND ---------------------------------
            if not tuning_tower_enabled:
                Logger.log('d', "Klipper Tuning Tower is Disabled")
            else:
                tower_settings = OrderedDict() # type: OrderedDict[str, Any]
                # Get all tuning tower setting values
                for tower_key, tower_setting in self.__tuning_tower_setting_key.items():
                    tower_settings[tower_key] = global_stack.getProperty(tower_setting, 'value')
                try: # Add tuning tower sequence to gcode
                    gcode_list[1] += (self._gcodeTuningTower(tower_settings) + self.comment + "\n")
                    gcode_changed = True

                except TypeError:
                    Logger.log('w', "Klipper tuning tower could not be processed.")
                    return # Stop on error

            ## Z OFFSET COMMAND -------------------------------------
            if not z_offset_enabled:
                Logger.log('d', "Klipper Z Offset Adjustment is Disabled")
                z_offset_layer_0 = 0
            else:
                z_offset_adjust_pattern = "SET_GCODE_OFFSET Z_ADJUST=%g " + self.comment
                z_offset_set_pattern = "SET_GCODE_OFFSET Z=%g " + self.comment

                z_offset_override = global_stack.getProperty('klipper_z_offset_set_enable', 'value')
                z_offset_layer_0 = global_stack.getProperty('klipper_z_offset_layer_0', 'value')

                if not z_offset_override:
                    Logger.log('d', "Klipper total z offset was not changed.")
                else:
                    z_offset_total = global_stack.getProperty('klipper_z_offset_set_total', 'value')
                    # Overrides any existing z offset with new value
                    # This will compound with any additional first layer z offset adjustment.
                    gcode_list[1] += z_offset_set_pattern % z_offset_total + "\n" # Applied after start gcode
                    gcode_changed = True
                    # Add z offset override warning
                    self._warning_msg.insert(0, "•  <i>Z Offset Override</i> is set to <b>%s mm</b>" % z_offset_total)

                if not z_offset_layer_0:
                    Logger.log('d', "Klipper first layer z offset was not changed.")
                else:
                    layer_0_height = global_stack.getProperty('layer_height_0', 'value')
                    # Matches z axis coordinate in gcode lines that haven't been processed
                    # Z offset only applies if z axis coordinate equals the layer 0 height;
                    # This is safer and necessary to avoid conflicts with settings such as z hop.
                    z_axis_regex = re.compile(r"^G[01]\s.*Z(%g)(?!.*%s)" % (layer_0_height, self.comment))

                    self._warning_msg.insert(0, "•  <i>Initial Layer Z Offset</i> will <b>%s</b> nozzle by <b>%s mm</b>" % (
                        "lower" if z_offset_layer_0 < 0 else "raise", z_offset_layer_0)) # Add to final warning message

            ## PRESSURE ADVANCE COMMAND -----------------------------
            if not pressure_advance_enabled and not smooth_time_enabled:
                Logger.log('d', "Klipper Pressure Advance Control is Disabled")

            else:
                # Extruder Settings
                apply_factor_per_feature = {}  # type: Dict[int, bool]
                extruder_factors = {}          # type: Dict[(int,str), float]
                current_factor = {}            # type: Dict[int, float]
                # Mesh Object Settings
                per_mesh_factors = {}          # type: Dict[(str,str), float]
                non_mesh_features = [*self.__pressure_advance_setting_key][8:] # SUPPORT, SKIRT, etc.

                smooth_time_factor = 0
                pressure_advance_factor = -1

                for extruder_stack in used_extruder_stacks: # Get settings for all active extruders
                    extruder_nr = int(extruder_stack.getProperty('extruder_nr', 'value'))

                    if not smooth_time_enabled:
                        Logger.log('d', "Klipper Pressure Advance Smooth Time is Disabled")
                    else:
                        smooth_time_factor = extruder_stack.getProperty('klipper_smooth_time_factor', 'value')

                    if not pressure_advance_enabled:
                        Logger.log('d', "Klipper Pressure Advance Factor is Disabled")
                    else:
                        pressure_advance_factor = extruder_stack.getProperty('klipper_pressure_advance_factor', 'value')
                        current_factor[extruder_nr] = pressure_advance_factor

                        # Gets feature settings for each extruder
                        for feature_key, setting_key in self.__pressure_advance_setting_key.items():
                            extruder_factors[(extruder_nr, feature_key)] = extruder_stack.getProperty(setting_key, 'value')
                            # Checks for unique feature values
                            if extruder_factors[(extruder_nr, feature_key)] != pressure_advance_factor:
                                apply_factor_per_feature[extruder_nr] = True # Flag to process gcode

                    try: # Add initial pressure advance command for all active extruders
                        new_gcode_commands += self._gcodePressureAdvance(
                            str(extruder_nr).strip('0'), pressure_advance_factor, smooth_time_factor) + "\n"

                    except TypeError:
                        Logger.log('w', "Klipper pressure advance values invalid: %s", str(pressure_adv_values))
                        return


                if pressure_advance_enabled:
                    ## Per Object Settings
                    # Gets printable mesh objects that are not support
                    nodes = [node for node in DepthFirstIterator(scene.getRoot())
                             if node.isSelectable()and not node.callDecoration('isNonThumbnailVisibleMesh')]
                    if not nodes:
                        Logger.log('w', "No valid objects in scene to process.")
                        return

                    for node in nodes:
                        mesh_name = node.getName() # Filename of mesh with extension
                        mesh_settings = node.callDecoration('getStack').getTop()
                        extruder_nr = int(node.callDecoration('getActiveExtruderPosition'))

                        # Get active feature settings for mesh object
                        for feature_key, setting_key in self.__pressure_advance_setting_key.items():
                            if mesh_settings.getInstance(setting_key) is not None:
                                mesh_setting_value = mesh_settings.getInstance(setting_key).value
                            else:
                                continue

                            # Save the children!
                            for feature in (
                                ["WALL-OUTER", "WALL-INNER", "SKIN", "FILL"] if feature_key == "_FACTORS"
                                    else ['WALL-OUTER', 'WALL-INNER'] if feature_key == "_WALLS"
                                    else ['SUPPORT', 'SUPPORT-INTERFACE'] if feature_key == "_SUPPORTS"
                                    else [feature_key]):

                                    per_mesh_factors[(mesh_name, feature)] = mesh_setting_value
                                    active_mesh_features.add(feature) # All per-object features
                                    apply_factor_per_feature[extruder_nr] = True # Flag to process gcode

                # Set gcode loop parameters
                if any(apply_factor_per_feature.values()):
                    for extruder_nr in list(apply_factor_per_feature):
                        active_extruder_list.add(extruder_nr)
                else:
                    pressure_advance_enabled = False


            ## POST-PROCESS GCODE LOOP ------------------------------
            # TODO: This should eventually get reworked into a function.
            if pressure_advance_enabled or (z_offset_layer_0 or extruder_fw_retraction):
                extruder_nr = start_extruder_nr
                current_layer_nr = -1
                current_mesh = None
                feature_type_error = False

                for layer_nr, layer in enumerate(gcode_list):
                    lines = layer.split("\n")
                    lines_changed = False
                    for line_nr, line in enumerate(lines):
                        apply_new_factor = False

                        if line.startswith(";LAYER:"):
                            try:
                                current_layer_nr = int(line[7:]) # Integer for current gcode layer
                            except ValueError:
                                Logger.log('w', "Could not get layer number: %s", line)

                            new_layer = bool(active_mesh_features) # Sanity check for mesh features

                        if z_offset_layer_0 and current_layer_nr == 0:
                            # Matches new line with z coordinate equal to layer 0 height
                            z_axis_change = z_axis_regex.fullmatch(line)

                            if z_axis_change:
                                # Inserts z offset command before matched line, then instructs klipper to
                                # revert the offset on the next z axis change even if the print is stopped.
                                lines.insert(line_nr + 1, z_offset_adjust_pattern % -(z_offset_layer_0))
                                lines[line_nr] = line + self.comment # Append line to prevent infinite match
                                lines.insert(line_nr, z_offset_adjust_pattern % z_offset_layer_0)
                                lines_changed = True

                        if len(active_extruder_list) > 1:
                            # Sets extruder number from tool change commands (T0,T1...)  
                            if line in ["T" + str(i) for i in active_extruder_list]:
                                try:
                                    extruder_nr = int(line[1:]) # Active extruder number
                                except ValueError:
                                    Logger.log('w', "Could not get extruder number: %s", line)

                                # Applies retraction values for the current extruder
                                if extruder_fw_retraction and current_layer_nr >= 0:
                                    lines.insert(line_nr + 1, extruder_fw_retraction[extruder_nr])
                                    lines_changed = True

                        if not pressure_advance_enabled:
                            if extruder_fw_retraction or (current_layer_nr <= 0 and z_offset_layer_0):
                                continue
                            else:
                                break

                        if line.startswith(";MESH:") and line[6:] != "NONMESH":
                            current_mesh = line[6:] # String for gcode mesh name 

                            if not feature_type_error:
                                continue

                            apply_new_factor = True # Command will insert before current line
                            feature_type_error = False

                        if line.startswith(";TYPE:"):
                            feature_type = line[6:] # String for gcode feature

                            if current_layer_nr <= 0 and feature_type != "SKIRT":
                                feature_type = "LAYER_0"

                            # Fixes when MESH name is not specified prior to its feature TYPE
                            # Mostly an issue in older cura versions.
                            if new_layer and feature_type in active_mesh_features:
                                feature_type_error = True
                                continue # Error corrected at next MESH line

                            apply_new_factor = True
                            line_nr += 1 # Command will insert after current line

                        if apply_new_factor:
                            # Sets current extruder value if no mesh setting exists
                            pressure_advance_factor = per_mesh_factors.get((current_mesh, feature_type),
                                                      extruder_factors[(extruder_nr, feature_type)])
                            new_layer = False

                            # Sets new factor if different from the active value
                            if pressure_advance_factor != current_factor.get(extruder_nr, None):
                                current_factor[extruder_nr] = pressure_advance_factor

                                lines.insert(line_nr, self._gcodePressureAdvance(
                                    str(extruder_nr).strip('0'), pressure_advance_factor))
                                lines_changed = True

                    ## Restores gcode layer formatting
                    if lines_changed:
                        gcode_list[layer_nr] = "\n".join(lines)
                        gcode_changed = True

            ## Adds new commands to start of gcode
            if not new_gcode_commands:
                Logger.log('d', "Klipper start gcode commands were not added.")
            else:
                gcode_list[1] = new_gcode_commands + "\n" + gcode_list[1]
                gcode_changed = True

        ## Finalize processed gcode
        if gcode_changed:
            self._showWarningMessage(60) # Display any active setting warnings
            gcode_list[0] += ";KLIPPERSETTINGSPROCESSED\n"
            gcode_dict[plate_id] = gcode_list
            setattr(scene, 'gcode_dict', gcode_dict)


    def gcodeSearch(self, gcode: str, command: str, ignore_comment: bool=False) -> bool:
        """Returns true if command exists in gcode string.

        Regex multi-line search for active or inactive gcode command string.
        Any characters on the line after the search string are ignored.
         * gcode: String containing gcode to search in.
         * command: String for gcode command to find.
         + ignore_comment: True includes commented command as a match.
        """
        # Command is assumed to be the start of the line, ignoring white space;
        # Technically treats any preceding character as a comment which is functionally
        # identical for this purpose because the command would be invalid anyway.
        result = re.search(r"(?mi)^(?P<comment>.*)(%s)[.]*" % re.escape(command), gcode)

        if result:
            line_match = result.group().lstrip(" \t")
            if line_match == command:
                Logger.log('i', "Active command found in gcode: '%s'", line_match)
                result = bool(result)
            elif result.group('comment') and ignore_comment:
                Logger.log('i', "Inactive command found in gcode: '%s'", line_match)
                result = line_match # Full line returned
            else:
                result = False

        return result

    def _gcodeUiSupport(self, gcode = List[str]) -> str:
        """Command string of commented print start temps.

        Allows fluidd/mainsail to detect gcode print temps when start gcode uses
        klipper macros without visible M190 and M109 gcode commands.
         * gcode: String containing gcode to search in.
        """
        bed_temp = self.settingWizard("material_bed_temperature_layer_0", 'value')
        nozzle_temp = self.settingWizard("material_print_temperature", 'value')
        nozzle_start_temp = self.settingWizard("material_print_temperature_layer_0", 'value')

        bed_temp_exists = self.gcodeSearch(gcode, "M190", True)
        nozzle_temp_exists = self.gcodeSearch(gcode, "M109", True)

        gcode_comment = ""
        if not bed_temp_exists:
            gcode_comment += ";M190 S%s %s\n" % (bed_temp, self.comment)
        if not nozzle_temp_exists:
            nozzle_temp = nozzle_start_temp if nozzle_start_temp > 0 else nozzle_temp
            gcode_comment += ";M109 S%s %s\n" % (nozzle_temp, self.comment)

        if gcode_comment:
           gcode_comment = ";Support for Klipper UI\n" + gcode_comment

        return gcode_comment

    def _gcodePressureAdvance(self, extruder_nr: str, pressure_advance: float=-1, smooth_time: float=0) -> str:
        """Returns enabled pressure advance settings as gcode command string.

        """
        gcode_command = "SET_PRESSURE_ADVANCE"

        if pressure_advance >= 0:
            gcode_command += " ADVANCE=%g" % pressure_advance

        if smooth_time > 0:
            gcode_command += " SMOOTH_TIME=%g" % smooth_time
        
        gcode_command += " EXTRUDER=extruder%s %s" % (extruder_nr, self.comment)

        return gcode_command

    def _gcodeVelocityLimits(self, velocity_limits: Dict[str, float]) -> str:
        """Returns enabled velocity settings as gcode command string.

        """
        # Remove disabled settings
        velocity_limits = {key: d for key, d in velocity_limits.items() if (
            key != "square_corner_velocity" and d > 0) or (
            key == "square_corner_velocity" and d >= 0)}

        if velocity_limits:
            gcode_command = "SET_VELOCITY_LIMIT "

            for key, value in velocity_limits.items():
                gcode_command += "%s=%d " % (key.upper(), value)

                if not self._override_on and (key == "square_corner_velocity" and value == 0):
                    self._warning_msg.append("•  Square Corner Velocity Limit = <b>0</b>")

            return gcode_command # TypeError msg if no return

    def _gcodeFirmwareRetraction(self, retraction_settings: Dict[str, float]) -> str:
        """Returns enabled firmware retraction settings as gcode command string.

        """
        # Remove disabled settings
        retraction_settings = {key: d for key, d in retraction_settings.items() if (
            key.endswith("speed") and d > 0) or (key.endswith("length") and d >= 0)}

        if retraction_settings:
            gcode_command = "SET_RETRACTION "

            for key, value in retraction_settings.items():
                gcode_command += "%s=%g " % (key.upper(), value) # Create gcode command

            return gcode_command # TypeError msg if no return

    def _gcodeInputShaper(self, shaper_settings: Dict[str, Any]) -> str:
        """Returns enabled input shaper settings as gcode command string.

        """
        if shaper_settings['shaper_type_x'] == shaper_settings['shaper_type_y']:
            shaper_settings['shaper_type'] = shaper_settings.pop('shaper_type_x')
            del shaper_settings['shaper_type_y'] # Use single command for both axes

        # Remove all disabled settings
        shaper_settings = {key: v for key, v in shaper_settings.items() if (
            key.startswith("type", 7) and v != "disabled") or (not key.startswith("type", 7) and v >= 0)}

        value_warnings = len([v for v in shaper_settings.values() if v == 0]) # Number of values set to 0

        if shaper_settings:
            gcode_command = "SET_INPUT_SHAPER "

            for key, value in shaper_settings.items():
                value = value.upper() if key.startswith("type", 7) else value
                gcode_command += "%s=%s " % (key.upper(), value) # Create gcode command

            if not self._override_on and value_warnings:
                self._warning_msg.append("•  <b>%d</b> Input Shaper setting(s) = <b>0</b>" % value_warnings)

            return gcode_command # TypeError msg if no return

    def _gcodeTuningTower(self, tower_settings: Dict[str, Any]) -> str:
        """Returns enabled tuning tower settings as gcode command string.

        Real-time string input validation done with regex patterns in setting definitions;
        Accepts only word characters but 'command' also allows spaces, 'single-quotes' and '='.
        'command' allows multiple words, up to arbitrary limit of 60 approved characters.
        'parameter' allows single word up to arbitrary limit of 40 word characters.
        """
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()
        gcode_settings = OrderedDict() # Preserve dict order in all Cura versions

        # Remove disabled and optional values
        for setting, value in tower_settings.items():
            if not (setting in ['skip', 'band'] and value == 0):
                gcode_settings[setting] = value

        # Strips any white space, quotes and '=' from ends of 'command' string
        gcode_settings['command'] = gcode_settings['command'].strip(" \t'=")
        # Add single quotes if 'command' has multiple words
        if len(gcode_settings['command'].split()) > 1:
            gcode_settings['command'] = "'%s'" % gcode_settings['command']

        gcode_command = "TUNING_TOWER "
        method = gcode_settings.pop('tuning_method')

        for key, value in gcode_settings.items():
            if method == "factor" and key in ['step_delta', 'step_height']:
                continue
            if method == "step" and key in ['factor', 'band']:
                continue

            gcode_command += "%s=%s " % (key.upper(), value)

        ## Final Tuning Tower Warning Message
        warning_msg = "<i>Tuning Tower is Active:</i><br/>%s<br/><br/>" % gcode_command
        if len(used_extruder_stacks) > 1:
            warning_msg += "<b><i>Tuning Tower</i> with multiple extruders could be unpredictable!</b><br/><br/>"
        warning_msg += "<i>Tuning tower calibration affects <b>all objects</b> on the build plate.</i>"

        self._warning_msg.append(warning_msg)

        return gcode_command # TypeError stop if no return

    def _setTuningTowerPreset(self) -> None:
        """Monitors and controls changes to tuning tower preset options.

        User settings overridden by a preset are preserved in config file in case Cura closes.
        Support for up to 3 user presets stored in Cura config sections.
        """
        if not self._global_container_stack: # Cura needs to finish loading
            return

        tuning_tower_enabled = self.settingWizard("klipper_tuning_tower_enable")

        if not tuning_tower_enabled:
            self._hideActiveMessages() # Hide any active tuning tower messages
            self._restoreUserSettings() # Ensure setting override is reset
            self._current_preset = None
            return

        elif not self._current_preset: # Tuning tower already enabled
            self._restoreUserSettings(announce = False)
            self._forceErrorCheck() # Default value error check
            self._hideActiveMessages()
            self.showMessage(
              "Tuning tower calibration affects <b>all objects</b> on the build plate.",
              "WARNING", "Klipper Tuning Tower is Active", 30) # Show startup warning

        preset_settings = {} #type: Dict[str, Any]
        apply_preset = False

        new_preset = self.settingWizard("klipper_tuning_tower_preset")
        override_enabled = self.settingWizard("klipper_tuning_tower_override")

        preset_changed = self._current_preset not in [None, new_preset]

        ## Suggested Settings Override
        if not override_enabled:
            self._restoreUserSettings(override_enabled)
            apply_preset = preset_changed

        elif preset_changed: # Reset setting override so user must re-enable it
            self._restoreUserSettings()
            return

        elif not self._override_on:
            Logger.log('d', "Tuning Tower Suggested Settings Enabled")
            self.hideMessageType(self._previous_msg, msg_type = 0)
            apply_preset = True

        # Gets integer of preset identity if any custom profiles are active
        active_custom_preset = int(new_preset[-1]) if new_preset.startswith("custom") else None

        ## Custom Preset Control
        # It is not necessary to constantly save changes to the active profile because
        # current values are handled by Cura and then saved upon changing profiles.
        if preset_changed:
            self._hideActiveMessages(msg_type = 1) # Hide neutral messages

            # Saves changes to custom preset when switching presets
            if self._current_preset.startswith("custom"):
                preset_key = int(self._current_preset[-1])
                for setting in self.__tuning_tower_setting_key.values():
                    setting = (preset_key, setting)
                    self.settingWizard(setting, action = "SaveCustom")

            # Applies current custom preset values
            if active_custom_preset:
                for setting, value in self._custom_presets.items():
                    if setting[0] == active_custom_preset: # Current preset settings
                        self.settingWizard(setting, value, "Set")

        self._current_preset = new_preset

        ## Klipper Preset Control
        if apply_preset and not active_custom_preset:
            self._forceErrorCheck()
            preset_message = None
            # Gets settings dict for enabled preset
            preset_settings = self.getPresetDefinition(new_preset, override_enabled) # type: Dict[str, Any]

            ## Preset Modifiers
            if new_preset == "pressure": # Update settings dict with any calculated values
                Logger.log('d', "Pressure Advance Tuning Tower Preset Enabled")
                preset_message = self._presetPressureAdvance(override = override_enabled) # type: List[str]
                preset_settings.update(self._presetPressureAdvance(preset_settings, override_enabled)) # type: Dict[str, Any]

            ## Next preset...

        if not preset_settings:
            return

        self._override_on = override_enabled # Save current override state

        settings_changed = ""

        for setting, value in preset_settings.items():
            setting_label = self.settingWizard(setting, action = "Get label")
            # TODO: Should eventually check every setting for conflicting children.
            if setting == "klipper_pressure_advance_factor":
                # Ensures all defined sub-settings are saved and cleared
                for subsetting in self.__pressure_advance_setting_key.values():
                    self.settingWizard(subsetting, value, "Save&Reset")

            if setting.startswith("klipper_tuning"):
                 self.settingWizard(setting, value, "Set") # No setting backup

            else: # Override is enabled
                self.settingWizard(setting, value, "Save&Set")
                if setting in self._user_settings: # Add name and value to string of changed settings
                    if not setting.startswith("klipper"):
                        setting_label = "<b>(Cura)</b> %s" % setting_label # Non-Klipper setting

                    settings_changed += "%s = %s<br />" % (setting_label, value)
                    Logger.log('d', "Klipper preset setting override: %s = %s", setting, value)

        ## Klipper Preset Message Box
        if settings_changed or preset_message:
            self._showPresetMessage(settings_changed, preset_message)


    def _presetPressureAdvance(self, preset_dict: Dict[str, Any]=None, override: bool=False) -> Any:
        """Modified dict or message with suggested values for pressure advance preset. 

        """
        preset_title = "Pressure Advance Tuning Tower"

        # Suggested factor from current retraction distance
        retract_length = self.settingWizard("klipper_retract_length") if (
                         self.settingWizard("machine_firmware_retract")) else (
                         self.settingWizard("retraction_amount"))

        suggested_factor = (0.02 if retract_length > 2.0 else 0.005) # Above 2 mm is likely bowden

        if preset_dict: # Change specific settings to suggested values
            for setting, value in preset_dict.items():
                current_value = self.settingWizard(setting)
                user_value = self.settingWizard(setting, "Get hasUserValue")
                # Applies suggested factor a unless user value already defined
                if override and setting.endswith("tower_factor"):
                    self.settingWizard(setting, action = "Save") # Backup value to restore
                    preset_dict[setting] = suggested_factor if not user_value else current_value

            return preset_dict

        elif override:
            # Suggested layer heights from current nozzle diameter
            nozzle_size = self.settingWizard("machine_nozzle_size")
            layer_heights = 0.04 * (nozzle_size * 0.75 // 0.04)
            layer_heights = "<b>%.2f - %.2f mm</b>  (%.2g mm Nozzle)" % (
                            layer_heights, layer_heights + 0.04, nozzle_size)
            # Returns suggested settings message
            message = (
              "<b>Some Printer Settings Need to be Set Manually:</b><br/><br/> \
              Print Speeds: <b>~100+ mm/s</b><br/> \
              Layer Height: %s<br/><br/>" % layer_heights)

        else: # Return default help message
            message = (
              "<b>Recommended <i>Factor</i> for Extruder Type:</b><br/><br/> \
              Direct Drive: <b>0.005</b><br/> \
              Bowden Extruder: <b>0.02</b><br /> \
              <i>Suggested for Current Retraction Distance:</i> <b>%s</b>" % suggested_factor)

        return [message, preset_title] # type: List[str]

    def _showPresetMessage(self, settings_changed: str=None, preset_msg: List[str]=None) -> None:
        """Shows message box with a preset message and/or any affected user settings.

         + settings_changed: String of every user setting affected by preset.
         + preset_msg: List of strings for preset message[0] and message title[1].
        """
        show_changes = [] # type: List[str]
        preset_title = None
        msg_title = "Suggested Settings Applied to Preset"

        if preset_msg and type(preset_msg) is list:
            try: preset_title = preset_msg[1] # Safety check
            except: preset_title = "Tuning Tower Preset"
            finally: preset_msg = preset_msg[0]

        if settings_changed:
            show_changes.append("<i>Settings Changed:</i><br /><br />") 
            show_changes.append("<br /><i>* Disable suggested settings to revert changes</i>")
            show_changes.insert(1, settings_changed)

            if preset_msg: # Preface with preset message
                show_changes.insert(0, preset_msg)

            show_changes = "".join(show_changes) # Convert message to single string

        elif preset_msg and not self._override_on: # Show only default preset message
            msg_title = preset_title
            show_changes = preset_msg

        if show_changes:
            self.showMessage(
              show_changes, "WARNING" if settings_changed else "NEUTRAL",
              msg_title,
              msg_time = 60 if settings_changed else 30,
              stack_msg = bool(settings_changed))


    def _getBackup(self, section: str="") -> Dict[Any, Any]:
        """Dict of settings stored in Cura user config.

        Uses existing config parser to get preference data from [klipper_settings] sections.
        The user settings backup is only needed if Cura closes with override enabled.
        Preset section 'preset<int>' returns user preset values or defaults if none exist.
         * section: Str for [klipper_settings_<str>] config section
        """
        ## Restricted: Uses Cura config parser for simplicity.
        config_parser = self._application.getPreferences()._parser

        config_key = "klipper_settings" + ("_%s" % section.lstrip("_") if section else "")
        config_settings = {} # type: Dict[str, Any]
        preset_settings = {} # type: Dict[str, Any]

        try: # Get preset section key
            preset_key = int(section[-1])
        except IndexError:
            preset_key = None

        try: # Get any settings in config section
            config_settings.update(config_parser.items(config_key))
        except configparser.NoSectionError:
            Logger.log('d', "[%s] not found in Cura config", config_key)
        except:
            Logger.logException('e', "Could not load Cura config file.")

        if not preset_key:
            return config_settings

        if not config_settings: # Get default preset settings
            config_settings = self.getPresetDefinition("default")

        for setting, value in config_settings.items():
            try: value = float(value) if value != None else "" # Convert number values back into float
            except ValueError: pass

            preset_settings[preset_key, setting] = value

        return preset_settings # type: Dict[(int, str), Any]

    def _restoreUserSettings(self, reset_override: bool=True, announce: bool=True) -> None:
        """Restore non tuning tower settings changed by preset.

        All user settings are restored from backup in real time.
         + announce: False disables status message when complete.
         + reset_override: True ensures suggested settings option is disabled.
        """
        if reset_override: # Disables suggested settings option if enabled
            self.settingWizard("klipper_tuning_tower_override", action = 'Reset')

        if not self._user_settings:
            if self._override_on:
                Logger.log('d', "No saved user settings to restore.")
        else:
            for setting, value in self._user_settings.items():
                self.settingWizard(setting, value, "Restore")

            self._user_settings.clear()
            Logger.log('d', "All user settings have been restored.")

            if announce and self._override_on:
                self.showMessage(
                  "Suggested tuning tower settings restored to original values.",
                  "POSITIVE", "Suggested Settings Disabled", 5)

            self._override_on = False


    def settingWizard(self, setting_key: str, new_value: Any=None, action: str='Get') -> Optional[Any]:
        """Action manager to control Cura settings and store values to local Cura config.

        Returns Cura setting from either global or active extruder stack.
        Clears setting instance if new set value same as default value.
        User setting changes are stored in Cura config under [klipper_settings].
        Custom preset values stored in Cura config under [klipper_settings_preset<int>].
         * setting_key: String for existing Cura setting.
         + new_value: Any value for setting_key or comparative for 'Save' action.
         + action: String specifying the operation for setting_key;
            Get (default)       : Return value from global or active extruder stack
            Get <str>           : Return any existing setting property (e.g. 'Get label')
            Save, Set, Save&Set : Save value to config and temp dict [and/or] set new_value
            SaveCustom          : Save current preset value to config and preset dict
            Restore             : Restore setting_key value from local config
            Reset, Save&Reset   : Save value to config and temp dict [and/or] reset to default value
        """
        # TODO: Only active extruder is currently supported.
        extruder_stack = self._application.getExtruderManager().getActiveExtruderStack()
        global_stack = self._application.getGlobalContainerStack()

        if not global_stack or not extruder_stack:
            return

        if isinstance(setting_key, tuple): # Get setting key if a custom preset tuple key
            custom_key = setting_key
            setting_key = setting_key[1]

        if action.startswith(("Save", "Restore")): # Set and check config key
            preferences = self._application.getPreferences()
            config_setting = "klipper_settings/%s" % setting_key

        extruder_setting = True if setting_key.startswith("extruder") else (
                           global_stack.getProperty(setting_key,'settable_per_extruder'))

        for stack in [extruder_stack] if extruder_setting else [global_stack]:
            current_value = stack.getProperty(setting_key, 'value')
            value_changed = current_value != new_value

            if action.startswith("Get"):
                if not action.endswith("Get"): # Action string contains property
                    property = "".join(action.split()).lower()[3:]
                    try: # Get requested property
                        if property.endswith("uservalue"): # Return true if user value
                            current_value = stack.hasUserValue(setting_key)
                        else: # Return value of property
                            current_value = stack.getProperty(setting_key, property)
                    except:
                        Logger.log('e', "Invalid Property '%s'", property)

                return current_value

            if action.startswith("Save"):
                if action.endswith("Custom"): # Value saved to global dict and preset in user config
                    config_setting = "klipper_settings_preset%i/%s" % (custom_key[0], custom_key[1])
                    self._custom_presets[custom_key] = current_value  # type: Dict[(int, str), Any]
                    preferences.addPreference(config_setting, None)
                    preferences.setValue(config_setting, str(current_value))

                elif value_changed: # New value saved to global dict and user config
                    self._user_settings[setting_key] = current_value  # type: Dict[str, Any]
                    preferences.addPreference(config_setting, None)
                    preferences.setValue(config_setting, current_value)

            if action == "Restore":
                # Clear redundant config backup
                preferences.removePreference(config_setting) # Logged by cura

                action += "Set" # Set original user value
                Logger.log('d', "%s restored to original value.", setting_key)

            if action.endswith("Set") and value_changed:
                stack.setProperty(setting_key, 'value', new_value)

                # Clear setting instance if new value same as default value
                if new_value == stack.getProperty(setting_key, 'default_value'):
                    action += "Reset"

            if action.endswith("Reset"): # Removes setting instance
                # TODO: Settings tied to multiple extruders may not get reset.
                stack.getTop().removeInstance(setting_key)


    def _showWarningMessage(self, msg_time: int=45) -> None:
        """Show final setting warnings as a single message box upon saving print file.

         + msg_time: Integer in seconds until message disappears.
        """
        if self._warning_msg:
            self.showMessage("<br/><br/>".join(self._warning_msg), "WARNING", "Klipper Settings Warnings", msg_time)
            self._warning_msg.clear()

    def _hideActiveMessages(self, msg_type: Optional[List[int]]=-3) -> None:
        """Hide potentially active plugin messages.

         + msg_type: Integer or list[int] from 0-3 for icon type(s) to hide;
                     Negative integer hides all types except the specified value.
        """
        if self._previous_msg:
            for message in self._active_msg_list:
                self.hideMessageType(message, msg_type)

    def showMessage(self, text: str, msg_type: Any=1, msg_title: str="Klipper Settings", msg_time: int=20, stack_msg: bool=False) -> None:
        """Display customized message box in Cura.

        Previous plugin message will be hidden by default.
        Maintains list of potentially active messages to be hidden when necessary.
        Message types only compatible with Cura version 4.10+
         * text: String to set message status.
         + msg_type: String or integer to set icon type; 0:POSITIVE 1:NEUTRAL 2:WARNING 3:ERROR
         + msg_title: String to set message title.
         + msg_time: Integer in seconds until message disappears.
         + stack_msg: True will not hide a previous message.
        """
        # TODO: Should really categorize plugin messages instead of just using universal types.
        if not isinstance(msg_type, int):
            msg_type = (
                0 if msg_type == "POSITIVE" else
                1 if msg_type == "NEUTRAL" else
                2 if msg_type == "WARNING" else 3 
            )

        if not stack_msg and self._previous_msg:
            self.hideMessageType(self._previous_msg, -3) # Hides a previous non-error message
            if self._previous_msg in self._active_msg_list:
                self._active_msg_list.remove(self._previous_msg)

        if self._cura_version <= Version("4.10.0"):
            display_message = Message(catalog.i18nc("@info:status", text),
                lifetime = msg_time,
                title = catalog.i18nc("@info:title", "<font size='+1'>%s</font>" % msg_title))
        else:
            display_message = Message(catalog.i18nc("@info:status", text),
                lifetime = msg_time,
                title = catalog.i18nc("@info:title", "<font size='+1'>%s</font>" % msg_title),
                message_type = msg_type)

        self._previous_msg = display_message # Saves copy of message
        if display_message not in self._active_msg_list: # Add to potentially active messages
            self._active_msg_list.append(display_message)

        display_message.show()

    def hideMessageType(self, message: Message, msg_type: Optional[List[int]]=1) -> None:
        """Hide previous message box only by specific icon types.

        Defaults to hiding neutral messages only.
        All message types are hidden if Cura version < 4.10.
         * message: Message object to hide if still active.
         + msg_type: Integer or list[int] from '0-3' for icon type(s) to be hidden;
                     Negative integer will hide all types except the specified value.
        """
        if not message:
            return

        legacy_version = self._cura_version <= Version("4.10.0")
        hide_types = [0, 1, 2, 3]
        active_msg_type = message.getMessageType() if not legacy_version else 1

        try:
            if msg_type < 0:
                hide_types.pop(abs(msg_type)) # Hides all other types
            else:
                hide_types = [msg_type] # Hides a specific type
        except TypeError:
            hide_types = list(msg_type) # type: List[int]

        if active_msg_type in hide_types or legacy_version:
            if message in self._active_msg_list:
                self._active_msg_list.remove(message)

            message.hide()


    def getPresetDefinition(self, new_preset: str, override: bool=False) -> Dict[str, Any]:
        """Dict of predefined setting values for tuning tower presets.

        Klipper Pressure Advance and Input Shaper calibrations currently supported.
         * new_preset: String for preset name
         + override: True includes any settings enabled by 'Apply Suggested Settings'.
        """
        # Tuple lists only necessary to guarantee OrderedDict in older Cura versions
        presets = [(
            'default', [
                ('klipper_tuning_tower_command', ''),
                ('klipper_tuning_tower_parameter', ''),
                ('klipper_tuning_tower_method', 'factor'),
                ('klipper_tuning_tower_start', 0),
                ('klipper_tuning_tower_skip', 0),
                ('klipper_tuning_tower_factor', 0),
                ('klipper_tuning_tower_band', 0),
                ('klipper_tuning_tower_step_delta', 0),
                ('klipper_tuning_tower_step_height', 0),
            ]),(
            'pressure', [
                ('klipper_tuning_tower_command', 'SET_PRESSURE_ADVANCE'),
                ('klipper_tuning_tower_parameter', 'ADVANCE'),
                ('klipper_tuning_tower_method', 'factor'),
                ('klipper_tuning_tower_start', 0),
                ('klipper_tuning_tower_skip', 0),
                ('klipper_tuning_tower_factor', 0),
                ('klipper_tuning_tower_band', 0),
                ('klipper_velocity_limits_enable', True),
                ('klipper_velocity_limit', 0),
                ('klipper_accel_limit', 500),
                ('klipper_accel_to_decel_limit', 0),
                ('klipper_corner_velocity_limit', 1.0),
                ('klipper_pressure_advance_enable', True),
                ('klipper_pressure_advance_factor', 0),
                ('acceleration_enabled', False)
            ]),(
            'accel', [
                ('klipper_tuning_tower_command', 'SET_VELOCITY_LIMIT'),
                ('klipper_tuning_tower_parameter', 'ACCEL'),
                ('klipper_tuning_tower_method', 'step'),
                ('klipper_tuning_tower_start', 1500),
                ('klipper_tuning_tower_skip', 0),
                ('klipper_tuning_tower_step_delta', 500),
                ('klipper_tuning_tower_step_height', 5),
                ('klipper_velocity_limits_enable', True),
                ('klipper_velocity_limit', 0),
                ('klipper_accel_limit', 0),
                ('klipper_accel_to_decel_limit', 7000),
                ('klipper_corner_velocity_limit', 1.0),
                ('klipper_pressure_advance_enable', True),
                ('klipper_pressure_advance_factor', 0),
                ('klipper_input_shaper_enable', True),
                ('klipper_shaper_freq_x', 0),
                ('klipper_shaper_freq_y', 0),
                ('acceleration_enabled', False)
            ])
            ## Next Preset:
        ]
        presets = OrderedDict(presets) # Convert and preserve setting order
        preset_dict = OrderedDict() # type: OrderedDict[str, Any]

        for preset in presets:

            if preset == new_preset:
                preset_dict.update(presets[preset]) 

                if not override: # Dict order isn't necessary
                    preset_dict = {k: v for k, v in preset_dict.items() if k.startswith('klipper_tuning')}

        return preset_dict


    # Dict order must be preserved
    __pressure_advance_setting_key = [
        ("_FACTORS", "klipper_pressure_advance_factor"),  ## [0-3] Parent settings
        ("_WALLS", "klipper_pressure_advance_wall"),
        ("_SUPPORTS", "klipper_pressure_advance_support"),
        ("LAYER_0", "klipper_pressure_advance_layer_0"),
        ("WALL-OUTER", "klipper_pressure_advance_wall_0"),  ## [4-7] Gcode mesh features
        ("WALL-INNER", "klipper_pressure_advance_wall_x"),
        ("SKIN", "klipper_pressure_advance_topbottom"),
        ("FILL", "klipper_pressure_advance_infill"),
        ("SUPPORT", "klipper_pressure_advance_support_infill"),  ## [8-11] Gcode non-mesh features
        ("SUPPORT-INTERFACE", "klipper_pressure_advance_support_interface"),
        ("PRIME-TOWER", "klipper_pressure_advance_prime_tower"),
        ("SKIRT", "klipper_pressure_advance_skirt_brim")
    ]
    __pressure_advance_setting_key = OrderedDict(__pressure_advance_setting_key) # Older cura compatibility

    __tuning_tower_setting_key = [
        ("tuning_method", "klipper_tuning_tower_method"),
        ("command", "klipper_tuning_tower_command"),
        ("parameter", "klipper_tuning_tower_parameter"),
        ("start", "klipper_tuning_tower_start"),
        ("skip", "klipper_tuning_tower_skip"),
        ("factor", "klipper_tuning_tower_factor"),
        ("band", "klipper_tuning_tower_band"),
        ("step_delta", "klipper_tuning_tower_step_delta"),
        ("step_height", "klipper_tuning_tower_step_height")
    ]
    __tuning_tower_setting_key = OrderedDict(__tuning_tower_setting_key)

    __velocity_limit_setting_key = {
        "velocity": "klipper_velocity_limit",
        "accel": "klipper_accel_limit",
        "accel_to_decel": "klipper_accel_to_decel_limit",
        "square_corner_velocity": "klipper_corner_velocity_limit"
    }
    __firmware_retraction_setting_key = {
        "retract_length": "klipper_retract_length",
        "unretract_extra_length": "klipper_retract_prime_length",
        "retract_speed": "klipper_retract_speed",
        "unretract_speed": "klipper_retract_prime_speed"
    }
    __input_shaper_setting_key = {
        "shaper_freq_x": "klipper_shaper_freq_x",
        "shaper_freq_y": "klipper_shaper_freq_y",
        "shaper_type_x": "klipper_shaper_type_x",
        "shaper_type_y": "klipper_shaper_type_y",
        "damping_ratio_x": "klipper_damping_ratio_x",
        "damping_ratio_y": "klipper_damping_ratio_y"
    }
