# KlipperSettingsPlugin v0.9.2 - Beta
# Copyright (c) 2022 J.Jarrard / JJFX
# The KlipperSettingsPlugin is released under the terms of the AGPLv3 or higher.
#
# ******************************************* CREDIT *************************************************
#   Key parts of this code are influenced by the great work of Cura legend Aldo Hoeben / fieldOfView  
#                           Thank you for all you do to help the community!                          
#
# KLIPPER SETTINGS PLUGIN
# -----------------------
# Creates new 'Klipper Settings' category at the bottom of settings list
# Compatible ONLY with Klipper Firmware
# Per-object setting support currently disabled for Cura versions prior to 4.7
#
# -------------------------------------------------
# Version | Release Notes & Features
# -------------------------------------------------
# v0.8.0  + Tested up to Cura version 5.0
#         | Pressure Advance Settings (v1.5)
#         | Tuning Tower Settings
#         | Velocity Limits Settings
# v0.8.1  + Fixed custom category icon
# v0.9.0  + Firmware Retraction Settings
#         | Input Shaper Settings
#         | Tuning Tower Presets feature
#         | Tuning Tower Suggested Settings feature
#         | Tuning Tower Preset: Pressure Advance
#         | Tuning Tower Preset: Ringing Tower
# v0.9.1  + Fixed crashing in older Cura versions
#         | Custom icon now only enabled for Cura 5.0+
#         | Improved preset and backup behavior
# v0.9.2  + P.A. Preset: Fixed incorrect parameter
#         | Preset layer height suggested from nozzle size


import os.path, json
import configparser # To parse settings backup in config file
from collections import OrderedDict # Ensure order of settings in all Cura versions
from typing import List, Optional, Any, Dict, Set, TYPE_CHECKING

from cura.CuraApplication import CuraApplication

try:
    from PyQt6.QtCore import QUrl
except ImportError: # Older cura versions
    from PyQt5.QtCore import QUrl

from UM.Qt.Bindings.Theme import Theme # Update theme with path to custom icon

from UM.Extension import Extension
from UM.Logger import Logger
from UM.Version import Version # Some features are disabled for older versions
from UM.Resources import Resources # Add local path to plugin resources dir

from UM.Settings.SettingDefinition import SettingDefinition     # Create and register setting definitions
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry

from UM.Message import Message # Display messages to user
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator # To parse per-object settings

from UM.i18n import i18nCatalog # Translations
i18n_catalog = i18nCatalog("cura")

if TYPE_CHECKING:
    from UM.OutputDevice.OutputDevice import OutputDevice

class KlipperSettingsPlugin(Extension):
    def __init__(self) -> None:
        super().__init__()

        self._application = CuraApplication.getInstance()
        self._cura_version = Version(self._application.getVersion())

        self._i18n_catalog = None  # type: Optional[i18nCatalog]

        self._settings_dict = {}   # type: Dict[str, Any]

        resource_path = os.path.join(os.path.dirname(__file__), "resources")
        # Resources.addSearchPath(resource_path) # Local resource path (future use)

        category_icon = self.updateCategoryIcon(resource_path, "Klipper") # Custom category icon

        self._category_key = "klipper_settings"
        self._category_dict = {
            "label": "Klipper Settings",
            "description": "Features and Settings Specific to Klipper Firmware",
            "type": "category",
            "icon": "%s" % category_icon
        }
        ## Message box placeholder
        self._previous_msg = None

        ## Globals for tuning tower functions
        self._user_settings = {}    # type: Dict[str, Any] # User settings to restore
        self._custom_preset = {}    # type: Dict[str, Any] # Preset values for comparison
        self._current_preset = None # type: str # Current preset name
        self._override_on = False   # type: bool # Override settings state

        try:
            with open(os.path.join(os.path.dirname(__file__), "klipper_settings.def.json"), encoding = "utf-8") as f:
                self._settings_dict = json.load(f, object_pairs_hook = OrderedDict)
        except:
            Logger.logException('e', "Could not load klipper settings definition")
            return

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)
        self._application.getPreferences().preferenceChanged.connect(self._fixCategoryVisibility)
        self._application.initializationFinished.connect(self._startActions)

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)

        # TODO: Signal to emit only when settings change
        self._application.getController().getScene().sceneChanged.connect(self._tuningPresets)

    def _startActions(self) -> None:
        # Checks visibility of new category
        self._fixCategoryVisibility()
        # Checks for user settings backed up in Cura config
        self._user_settings = self._getBackup() # type: Dict[str, Any]
        # Disables tuning tower preset override
        self._restoreUserSettings(announce = False)
        # Default placeholders for custom preset
        self._custom_preset.update(self.getTowerDefaults())

    def _onContainerLoadComplete(self, container_id: str) -> None:
        """Parses loaded containers on startup to find definition container.

        Registers new 'Klipper Settings' category to import setting definition json.
        """
        if not ContainerRegistry.getInstance().isLoaded(container_id):
            return # Skip containers that could not be loaded to avoid infinite findContainers() loop
        try:
            container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
            self._container = container
        except IndexError:
            return # Container no longer exists

        if not isinstance(container, DefinitionContainer) or container.getMetaDataEntry('type') == "extruder":
            return # Skip non-definition containers

        # Create new settings category
        klipper_category = SettingDefinition(self._category_key, container, None, self._i18n_catalog)
        klipper_category.deserialize(self._category_dict)

        container.addDefinition(klipper_category) # Register category setting definition

        try: # Make sure new category actually exists
            klipper_category = container.findDefinitions(key=self._category_key)[0]
            self._category = klipper_category
        except IndexError:
            Logger.log('e', "Could not find settings category: '%s'", self._category_key)
            return

        # Add all setting definitions to new category
        for setting_key in self._settings_dict.keys():
            setting_definition = SettingDefinition(setting_key, container, klipper_category, self._i18n_catalog)
            setting_definition.deserialize(self._settings_dict[setting_key])

            klipper_category._children.append(setting_definition)
            container._definition_cache[setting_key] = setting_definition

            if setting_definition.children:
                self._updateAddedChildren(container, setting_definition)

        container._updateRelations(klipper_category) # Update relations of all category settings

    def _updateAddedChildren(self, container: DefinitionContainer, setting_definition: SettingDefinition) -> None:
        ## Update definition cache for setting definition children
        for child in setting_definition.children:
            container._definition_cache[child.key] = child

            if child.children:
                self._updateAddedChildren(container, child)

    def _fixCategoryVisibility(self, preference: str = "general/visible_settings") -> None:
        """Ensure category is visibile at start and when visibility changes.

        """
        if preference != "general/visible_settings":
            return

        preferences = self._application.getPreferences()
        visible_settings = preferences.getValue(preference)

        if not visible_settings:
            return # Empty list fixed once user adds a visibile setting

        if self._category_key not in visible_settings:
            visible_settings += ";%s" % self._category_key

            preferences.setValue(preference, visible_settings) # Category added to visible settings

    def _fixValueErrorBug(self) -> None:
        """Forces error check for tuning tower setting values.

        Fixes apparent Cura bug not recognizing default values as an error.
        """
        machine_manager = self._application.getMachineErrorChecker()

        for key, setting in self.__tuning_tower_setting_key.items():
            machine_manager.startErrorCheckPropertyChanged(setting, "value")

    def updateCategoryIcon(self, icon_path: str, icon_name: str) -> str:
        """Updates theme with local path to custom category icon

        Only working for Cura 5.0+.
        If new icon can't be used a default existing icon is returned.
          icon_path: String for local dir that contains an 'icons' directory
          icon_name: String for name of icon file without extension
        Returns: String for icon to set
        """
        legacy_version = self._cura_version < Version("5.0.0")
        icon_path = os.path.join(icon_path, "icons", "%s.svg" % icon_name)

        category_icon = "plugin" # Default Cura icon if new icon fails to load

        if not os.path.exists(icon_path):
            Logger.log('d', "Custom icon file could not be found.")
        elif legacy_version:
            Logger.log('d', "Custom icon not compatible with Cura version %s", self._cura_version)
        else:
            current_theme = Theme.getInstance()
            category_icon = icon_name

            # Add new icon path to current theme (thanks batman)
            if icon_name not in current_theme._icons['default']:
                current_theme._icons['default'][icon_name] = QUrl.fromLocalFile(icon_path)

        return category_icon


    def _filterGcode(self, output_device: "OutputDevice") -> None:
        """Inserts enabled Klipper settings into final gcode.

        """
        scene = self._application.getController().getScene()
        global_stack = self._application.getGlobalContainerStack()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()

        if not global_stack or not used_extruder_stacks:
            return

        # Disable per-object settings for older Cura versions
        support_per_object_settings = self._cura_version >= Version("4.7.0")

        # Retrieve state of klipper setting controls (bool)
        firmware_retraction_enabled = global_stack.getProperty('machine_firmware_retract', 'value')
        pressure_advance_enabled = global_stack.getProperty('klipper_pressure_advance_enable', 'value')
        velocity_limits_enabled = global_stack.getProperty('klipper_velocity_limits_enable', 'value')
        input_shaper_enabled = global_stack.getProperty('klipper_input_shaper_enable', 'value')
        tuning_tower_enabled = global_stack.getProperty('klipper_tuning_tower_enable', 'value')

        gcode_dict = getattr(scene, 'gcode_dict', {})
        if not gcode_dict: # this also checks for an empty dict
            Logger.log('w', "Scene has no gcode to process")
            return

        # Pressure advance command template
        gcode_cmd_pattern = "SET_PRESSURE_ADVANCE ADVANCE=%g EXTRUDER=extruder%s"
        gcode_cmd_pattern += " ;KlipperSettingsPlugin"

        dict_changed = False

        for plate_id in gcode_dict:
            gcode_list = gcode_dict[plate_id]
            if len(gcode_list) < 2:
                Logger.log('w', "Plate %s does not contain any layers", plate_id)
                continue
            if ";KLIPPERSETTINGSPROCESSED\n" in gcode_list[0]:
                Logger.log('d', "Plate %s has already been processed", plate_id)
                continue


            ## KLIPPER TUNING TOWER COMMAND -------------------------
            if not tuning_tower_enabled:
                Logger.log('d', "Klipper Tuning Tower is Disabled")
            else:
                tower_settings = {} # type: Dict[str, Any]
                # Get tuning tower settings to pass to function
                for tower_key, tower_setting in self.__tuning_tower_setting_key.items():
                    tower_settings[tower_key] = global_stack.getProperty(tower_setting, 'value')

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeTuningTower(tower_settings) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('e', "Tuning tower command could not be processed")
                    return # Stop on error

            ## KLIPPER VELOCITY LIMITS COMMAND ----------------------
            if not velocity_limits_enabled:
                Logger.log('d', "Klipper Velocity Limit Control is Disabled")
            else:
                velocity_limits = {} # type: Dict[str, int]
                # Get velocity settings to pass to function
                for limit_key, limit_setting in self.__velocity_limit_setting_key.items():
                    velocity_limits[limit_key] = global_stack.getProperty(limit_setting, 'value')

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeVelocityLimits(velocity_limits) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('d', "Klipper velocity limits were not changed")

            ## KLIPPER FIRMWARE RETRACTION COMMAND ------------------
            if not firmware_retraction_enabled:
                Logger.log('d', "Firmware Retraction is Disabled")
            else:
                retraction_settings = {} # type: Dict[str, float]
                # Get firmware retraction settings to pass to function
                for retract_key, retract_setting in self.__firmware_retraction_setting_key.items():
                    retraction_settings[retract_key] = global_stack.getProperty(retract_setting, 'value')

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeFirmwareRetraction(retraction_settings) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('d', "Firmware retraction settings were not changed")

            ## KLIPPER INPUT SHAPER COMMAND -------------------------
            if not input_shaper_enabled:
                Logger.log('d', "Input Shaper is Disabled")
            else:
                shaper_settings = {} # type: Dict[str, Any]
                # Get input shaper settings to pass to function
                for shaper_key, shaper_setting in self.__input_shaper_setting_key.items():
                    shaper_settings[shaper_key] = global_stack.getProperty(shaper_setting, 'value')

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeInputShaper(shaper_settings) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('d', "Input shaper settings were not changed")

            ## KLIPPER PRESSURE ADVANCE COMMAND ---------------------
            if not pressure_advance_enabled:
                Logger.log('d', "Klipper Pressure Advance Control is Disabled")
                break

            ## Extruder Dictionaries
            apply_factor_per_feature = {}  # type: Dict[int, bool]
            current_advance_factors = {}   # type: Dict[int, float]
            per_extruder_settings = {}     # type: Dict[(int,str), float]
            ## Mesh Object Dictionaries
            apply_factor_per_mesh = {}     # type: Dict[str, bool]
            per_mesh_settings = {}         # type: Dict[(str,str), float]

            non_mesh_features = [*self.__pressure_advance_setting_key][8:] # SUPPORT, SKIRT, etc.
            parent_setting_key = "klipper_pressure_advance_factor" # Primary setting

            # Get settings for all active extruders
            for extruder_stack in used_extruder_stacks:
                extruder_nr = int(extruder_stack.getProperty('extruder_nr', 'value'))
                pressure_advance_factor = extruder_stack.getProperty(parent_setting_key, 'value')
                current_advance_factors[extruder_nr] = pressure_advance_factor

                try: # Add primary value of each extruder to start of gcode
                    gcode_list[1] = gcode_list[1] + gcode_cmd_pattern % (
                        pressure_advance_factor, str(extruder_nr).strip('0')) + "\n"

                    dict_changed = True

                except TypeError:
                    Logger.log('e', "Invalid pressure advance value: '%s'", pressure_advance_factor)
                    return

                # Get all feature settings for each extruder
                for feature_key, setting_key in self.__pressure_advance_setting_key.items():
                    per_extruder_settings[(extruder_nr, feature_key)] = extruder_stack.getProperty(setting_key, 'value')

                    # Check for unique feature settings
                    if per_extruder_settings[(extruder_nr, feature_key)] != pressure_advance_factor:
                        apply_factor_per_feature[extruder_nr] = True # Flag to process gcode

            # Get settings for all printable mesh objects that are not support
            nodes = [node for node in DepthFirstIterator(scene.getRoot())
                     if node.isSelectable()and not node.callDecoration('isNonThumbnailVisibleMesh')]
            if not nodes:
                Logger.log('w', "No valid objects in scene to process")
                return

            for node in nodes:
                if not support_per_object_settings:
                    Logger.log('d', "Per-object settings disabled for Cura version %s", self._cura_version)
                    break # Use extruder values for older Cura versions

                mesh_name = node.getName() # Filename of mesh with extension
                mesh_settings = node.callDecoration('getStack').getTop()
                extruder_nr = int(node.callDecoration('getActiveExtruderPosition'))

                # Get all feature settings for each mesh object
                for feature_key, setting_key in self.__pressure_advance_setting_key.items():
                    if mesh_settings.getInstance(setting_key) is not None:
                        mesh_setting_value = mesh_settings.getInstance(setting_key).value
                    else:
                        # Use extruder value if no per object setting is defined
                        if (mesh_name, feature_key) not in per_mesh_settings:
                            per_mesh_settings[(mesh_name, feature_key)] = per_extruder_settings[(extruder_nr, feature_key)]

                        continue

                    # Save the children!
                    for feature in (
                        [*self.__pressure_advance_setting_key][4:8] if feature_key == "_FACTORS"
                            else ['WALL-OUTER', 'WALL-INNER'] if feature_key == "_WALLS"
                            else ['SUPPORT', 'SUPPORT-INTERFACE'] if feature_key == "_SUPPORTS"
                            else [feature_key]):

                        if mesh_setting_value != per_extruder_settings[(extruder_nr,feature)]:
                            if mesh_setting_value != per_mesh_settings.get((mesh_name,feature)):
                                apply_factor_per_mesh[(mesh_name,feature)] = True
                                per_mesh_settings[(mesh_name,feature)] = mesh_setting_value

                                apply_factor_per_feature[extruder_nr] = True # Flag to process gcode


            ## Post-process gcode loop
            if any(apply_factor_per_feature.values()):
                active_extruder_list = [*apply_factor_per_feature] # type: List[int]
                active_mesh_list = [*zip(*per_mesh_settings)][0]   # type: List[str]

                extruder_nr = active_extruder_list[0] # Start with first extruder
                current_mesh = None
                current_layer_nr = -1
                feature_type_error = False

                for layer_nr, layer in enumerate(gcode_list):
                    lines = layer.split("\n")
                    lines_changed = False
                    for line_nr, line in enumerate(lines):

                        if line.startswith(";LAYER:"):
                            try:
                                current_layer_nr = int(line[7:]) # Get gcode layer number
                            except ValueError:
                                Logger.log('w', "Could not parse layer number: ", line)
                            # Layer check to detect per object feature errors
                            new_layer = bool(support_per_object_settings)

                        if len(active_extruder_list) > 1:
                            # Check for tool change gcode command (T0,T1...)
                            if line in ["T" + str(i) for i in active_extruder_list]:
                                try:
                                    extruder_nr = int(line[1:]) # Get active extruder number from gcode
                                except ValueError:
                                    Logger.log('w', "Could not parse extruder number: ", line)

                        if line.startswith(";MESH:") and line[6:] in active_mesh_list:
                            current_mesh = line[6:] # Set gcode mesh name

                            # Fix for when Cura rudely declares TYPE before MESH in new layer
                            if feature_type_error:
                                feature_type = "LAYER_0" if current_layer_nr <= 0 else feature_type
                                if per_mesh_settings[(current_mesh, feature_type)] != current_advance_factors[extruder_nr]:
                                    current_advance_factors[extruder_nr] = per_mesh_settings[(current_mesh, feature_type)]

                                    lines.insert(line_nr, gcode_cmd_pattern % (
                                        current_advance_factors[extruder_nr], str(extruder_nr).strip('0')))

                                    lines_changed = True # Corrected command inserted into gcode

                                feature_type_error = new_layer = False
                                continue # Clear error and resume

                        if line.startswith(";TYPE:"):
                            feature_type = line[6:] # Get gcode feature type

                            # Check for unknown mesh feature in a new layer
                            if new_layer and feature_type not in non_mesh_features:
                                feature_type_error = True
                                continue # Error corrected at next MESH line

                            if current_layer_nr <= 0 and feature_type != "SKIRT":
                                feature_type = "LAYER_0"

                            if apply_factor_per_mesh.get((current_mesh, feature_type), False):
                                pressure_advance_factor = per_mesh_settings[(current_mesh, feature_type)]
                            else:
                                pressure_advance_factor = per_extruder_settings[(extruder_nr, feature_type)]

                            new_layer = False # Reset layer check
                            # Insert gcode command if current extruder value has changed
                            if pressure_advance_factor != current_advance_factors.get(extruder_nr, None):
                                current_advance_factors[extruder_nr] = pressure_advance_factor

                                lines.insert(line_nr + 1, gcode_cmd_pattern % (
                                    pressure_advance_factor, str(extruder_nr).strip('0')))

                                lines_changed = True # Command inserted into gcode

                    if lines_changed:
                        gcode_list[layer_nr] = "\n".join(lines)
                        dict_changed = True

        if dict_changed:
            gcode_list[0] += ";KLIPPERSETTINGSPROCESSED\n"
            gcode_dict[plate_id] = gcode_list
            setattr(scene, 'gcode_dict', gcode_dict)

    def _gcodeVelocityLimits(self, velocity_limits: Dict[str, float]) -> str:
        """Parse enabled velocity settings into gcode command string.

        """
        # Remove disabled settings
        velocity_limits = {key: d for key, d in velocity_limits.items() if (
            key != "square_corner_velocity" and d > 0) or (
            key == "square_corner_velocity" and d >= 0)}

        if len(velocity_limits) > 0:
            gcode_command = "SET_VELOCITY_LIMIT "

            for key, value in velocity_limits.items():
                gcode_command += "%s=%d " % (key.upper(), value) # Create gcode command
                
                if key == "square_corner_velocity" and value == 0:
                    self.showMessage(
                      "WARNING: Square Corner Velocity is set to 0<br /><br /> <i>To disable slicer control, value must be -1</i>",
                      "WARNING", "Klipper Velocity Limits", 25)

            return gcode_command # TypeError msg if no return

    def _gcodeFirmwareRetraction(self, retraction_settings: Dict[str, float]) -> str:
        """Parses enabled firmware retraction settings into gcode command string.

        """
        # Remove disabled settings
        retraction_settings = {key: d for key, d in retraction_settings.items() if (
            key.endswith("speed") and d > 0) or (
            key.endswith("length") and d >= 0)}

        if len(retraction_settings) > 0:
            gcode_command = "SET_RETRACTION "

            for key, value in retraction_settings.items():
                gcode_command += "%s=%g " % (key.upper(), value) # Create gcode command

            return gcode_command # TypeError msg if no return

    def _gcodeInputShaper(self, shaper_settings: Dict[str, Any]) -> str:
        """Parses enabled input shaper settings into gcode command string.

        """
        if shaper_settings['shaper_type_x'] == shaper_settings['shaper_type_y']:
            shaper_settings['shaper_type'] = shaper_settings.pop('shaper_type_x')
            del shaper_settings['shaper_type_y'] # Use single command for both axes

        # Remove all disabled settings
        shaper_settings = {key: v for key, v in shaper_settings.items() if (
            key.startswith("type", 7) and v != "disabled") or (
            not key.startswith("type", 7) and v >= 0)}

        warning_val = len([v for v in shaper_settings.values() if v == 0]) # Number of values = 0

        if len(shaper_settings) > 0:
            gcode_command = "SET_INPUT_SHAPER "

            for key, value in shaper_settings.items():

                gcode_command += "%s=%s " % (key.upper(), value) # Create gcode command

            if warning_val > 0:
                self.showMessage(
                  "WARNING: %d input shaper value(s) set to 0.<br /><br /> <i>To disable slicer control, value must be -1</i>" % warning_val,
                  "WARNING", "Klipper Input Shaper", 25)

            return gcode_command # TypeError msg if no return


    def _gcodeTuningTower(self, tower_settings: Dict[str, str]) -> str:
        """Parses enabled tuning tower settings into gcode command string.

        """
        # Remove disabled and optional values
        tower_settings = {key: i for key, i in tower_settings.items() if not (
            key in ['skip', 'band'] and i == 0)}

        ## Most input validation done with setting definition regex patterns
        tower_settings['command'] = tower_settings['command'].strip(" '=")
        # Add single quotes if command has multiple words
        if len(tower_settings['command'].split()) > 1:
            tower_settings['command'] = "'%s'" % tower_settings['command']

        gcode_command = "TUNING_TOWER "
        method = tower_settings.pop('tuning_method')

        for key, value in tower_settings.items():
            if method == "factor" and key in ['step_delta', 'step_height']:
                continue
            if method == "step" and key in ['factor', 'band']:
                continue

            gcode_command += "%s=%s " % (key.upper(), value)

        self.showMessage(
          "Tuning tower settings will affect <b>all objects</b> on the build plate.",
          "NEUTRAL", "Klipper Tuning Tower Enabled")

        return gcode_command # TypeError stop if no return

    def _tuningPresets(self, ignore_me = None) -> None:
        """Controls all changes to tuning tower preset settings.

        Any user settings changed by preset values are preserved and restored.
        """
        # TODO: Signal that only emits when settings are changed (remove ignore)
        #     : Consider forcing visibility of override settings??
        global_stack = self._application.getGlobalContainerStack()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()

        if not global_stack or not used_extruder_stacks:
            return

        tuning_tower_enabled = global_stack.getProperty('klipper_tuning_tower_enable', 'value')

        if not tuning_tower_enabled:
            # Reset override and hide messages if tuner tower disabled
            self._restoreUserSettings()
            self._current_preset = None

            if self._previous_msg:
                self._previous_msg.hide()

            return

        elif not self._current_preset:
            self._fixValueErrorBug() # Force default value error check
            self.showMessage(
              "Tuning tower settings will affect <b>all objects</b> on the build plate.",
              "WARNING", "Klipper Tuning Tower Enabled", 60) # Start warning


        new_preset = global_stack.getProperty('klipper_tuning_tower_preset', 'value')
        override = global_stack.getProperty('klipper_tuning_tower_override', 'value')

        preset_settings = {} #type: Dict[str, Any]
        preset_changed = self._current_preset not in [None, new_preset]
        apply_preset = False

        if not override:
            self._restoreUserSettings()
            apply_preset = preset_changed

            self._override_on = False

        elif preset_changed: # Reset override so user must re-enable it
            self._restoreUserSettings()
            return

        elif not self._override_on:
            apply_preset = True


        if preset_changed:
            # Save/restore tuning tower settings for 'custom' preset
            if self._current_preset == "custom":
                for setting in self.__tuning_tower_setting_key.values():
                    self.settingWizard(setting, action = "SaveCustom")

            elif new_preset == "custom":
                for setting, value in self._custom_preset.items():
                    self.settingWizard(setting, value, action = "Restore")

            ## User preset action messages
            if new_preset == "pressure":
                # Suggest layer height range from current nozzle diameter
                for extruder in used_extruder_stacks:
                    nozzle_size = extruder.getProperty('machine_nozzle_size', 'value')
                    layer_heights = 0.04 * (nozzle_size * 0.75 // 0.04)
                    layer_heights = "<b>%.2f - %.2f mm</b>  (%.2g mm Nozzle)" % (
                                    layer_heights, layer_heights + 0.04, nozzle_size)

                self.showMessage(
                  "<b>The following settings must be set manually.</b><br/><br/> <i>Suggested Values for Pressure Advance Calibration:</i>.<br/><br/> <b>Tuning Tower Factor:</b><br/><i>Direct Drive:</i> <b>'.005'</b> | <i>Bowden:</i> <b>'.020'</b><br /><br /><b>Printer Settings:</b><br/><i>Print Speed:</i> <b>~100+ mm/s</b><br/><i>Layer Height:</i> %s" % layer_heights,
                  "NEUTRAL", "Adjust Printer-Specific Settings", 60)
            ## Next preset message...

            # Hide last neutral message when preset changed
            elif self._previous_msg:
                self.hideMessageType(self._previous_msg, msg_type = 1)


        self._current_preset = new_preset

        if apply_preset:
            self._fixValueErrorBug() # Ensure user can't slice with value errors

            preset_settings = self.getPresetDefinition(new_preset, override)

        if not preset_settings:
            return

        self._override_on = override


        show_changes = ""

        for setting, value in preset_settings.items():
            if setting == "klipper_pressure_advance_factor":
                # Ensure all subsettings are cleared
                for subsetting in self.__pressure_advance_setting_key.values():
                    self.settingWizard(subsetting, 0, "Save&Clear")

            if setting.startswith("klipper_tuning"):
                self.settingWizard(setting, value, "Set") # No backup

            else: # Override enabled
                self.settingWizard(setting, value, "Save&Set")

                if setting in self._user_settings:
                    # List names and values of changed settings
                    setting_label = global_stack.getProperty(setting, 'label')
                    if not setting.startswith("klipper"):
                        setting_label = "<b>(Cura)</b> %s" % setting_label # Non-Klipper settings

                    show_changes += "%s = %s<br />" % (setting_label, value)
                    Logger.log('d', "User setting changed: %s = %s", setting, value)

        if show_changes:
            self.showMessage(
              "<b>Settings Changed:</b><br /><br />%s<br /><i>* Disable suggested settings to revert changes</i>" % show_changes,
              "WARNING", "Tuning Tower Setting Override", 60)


    def settingWizard(self, setting_key: str, new_value: Any=None, action: str="Save") -> None:
        """Backup, remove or set Cura setting values.

          setting_key: String of an existing Cura setting.
          new_value: New value for setting_key, or comparison value for Save.
          action: String specifying the operation to perform.
            Save (Default)    : Backup current value to dict and Cura config.
            SaveCustom        : Backup current 'tuning tower' value in custom dict.
            Restore           : Restore state from backup.
            Clear, Save&Clear : Backup and/or reset to default value.
            Set, Save&Set     : Backup and/or set new_value.
        """
        # TODO: Full support for multiple extruders not yet implemented!

        global_stack = self._application.getGlobalContainerStack()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()

        if not global_stack or not used_extruder_stacks:
            return

        preferences = self._application.getPreferences()
        extruder_setting = global_stack.getProperty(setting_key,'settable_per_extruder')

        for stack in (used_extruder_stacks if extruder_setting else [global_stack]):
            current_value = stack.getProperty(setting_key, 'value')
            change_value = current_value != new_value

            if action.startswith("Save") and change_value:
                if action.endswith("Custom"):
                    self._custom_preset[setting_key] = current_value # global: Dict[str, Any]
                else:
                    self._user_settings[setting_key] = current_value # global: Dict[str, Any]
                    # Additional backup stored in Cura config file
                    preferences.addPreference("klipper_settings/%s" % setting_key, "")
                    preferences.setValue("klipper_settings/%s" % setting_key, current_value)

            if action.endswith("Set") and change_value:
                stack.setProperty(setting_key, 'value', new_value) # Set new value

            if action.endswith("Clear"): # All instances removed for reliability
                stack.getTop().removeInstance(setting_key) # Remove setting instance

            if action == "Restore":
                backup_exists = preferences._findPreference("klipper_settings/%s" % setting_key)

                stack.setProperty(setting_key, 'value', new_value) # Restore user value

                if backup_exists:
                    preferences.removePreference("klipper_settings/%s" % setting_key)

                # Ensure setting instance is cleared if value same as default value.
                if new_value == stack.getProperty(setting_key, 'default_value'):
                    stack.getTop().removeInstance(setting_key)

    def getTowerDefaults(self) -> Dict[str, Any]:
        """Dict of default values for tuning tower settings.

        """
        global_stack = self._application.getGlobalContainerStack()
        default_settings = {} # type: Dict[str, Any]

        for setting in self.__tuning_tower_setting_key.values():
            default_settings[setting] = global_stack.getProperty(setting, 'default_value')

        return default_settings

    def _getBackup(self) -> Dict[str, Any]:
        """Dict of any backup settings saved to config file.

        Uses existing configparser data to get preferences under klipper_settings section.
        Backup only necessary if Cura crashes or force closed with override enabled.
        """
        ## Restricted access is best access.
        config_parser = self._application.getPreferences()._parser

        settings_backup = {} # type: Dict[str, Any]

        try:
            settings_backup.update(config_parser.items("klipper_settings"))
        except configparser.NoSectionError:
            Logger.log('e', "Could not find klipper_settings in config file.")

        if settings_backup:
            Logger.log('d', "Backup settings retrieved from config file.")

        return settings_backup

    def _restoreUserSettings(self, announce: bool=True) -> None:
        """Restore non tuning tower settings changed by preset.

          announce: False disables status message when complete.
        """
        # Disable setting override if enabled
        self.settingWizard('klipper_tuning_tower_override', action = "Clear")

        if self._user_settings:

            for setting, value in self._user_settings.items():
                self.settingWizard(setting, value, "Restore")

            self._user_settings.clear() # Clear backup
            Logger.log('d', "User settings have been restored.")

            if announce and self._override_on:
                self.showMessage(
                  "Suggested tuning tower settings restored to original values.",
                  "POSITIVE", "Suggested Settings Disabled", 5)

    def showMessage(self, text: str, msg_type = 1, msg_title: str = "Klipper Settings", msg_time: int = 15, hide_msg = None) -> None:
        """Helper function to display messages to user.

        Message types only compatible with Cura version 4.10+
          text: String to set message status.
          msg_type: String to set icon type ([0-3] or POSITIVE, NEUTRAL, WARNING, ERROR).
          msg_title: String to set message title.
          msg_time: Integer in seconds until message disappears.
        """
        legacy_version = self._cura_version <= Version("4.10.0")

        if not isinstance(msg_type, int):
            msg_type = (
                0 if msg_type == "POSITIVE" else
                1 if msg_type == "NEUTRAL" else
                2 if msg_type == "WARNING" else 3 
            )
        if self._previous_msg:
            self._previous_msg.hide() # Prevent message stacking

        if legacy_version:
            display_message = Message(i18n_catalog.i18nc("@info:status", text),
                lifetime = msg_time,
                title = i18n_catalog.i18nc("@info:title", "<font size='+1'>%s</font>" % msg_title))
        else:
            display_message = Message(i18n_catalog.i18nc("@info:status", text),
                lifetime = msg_time,
                title = i18n_catalog.i18nc("@info:title", "<font size='+1'>%s</font>" % msg_title),
                message_type = msg_type)

        display_message.show()
        self._previous_msg = display_message

    def hideMessageType(self, message: Message = None, msg_type = 1) -> None:
        """Hides previous messages by type.

        All message types are hidden if Cura version < 4.10
        """
        legacy_version = self._cura_version <= Version("4.10.0")

        if message:
            if not legacy_version:
                if message.getMessageType() == msg_type:
                    message.hide()
            else:
                message.hide()


    def getPresetDefinition(self, new_preset: str, override: bool=False) -> Dict[str, Any]:
        """Dict of pre-defined setting values for tuning tower presets.

          new_preset: String for preset name
          override: True includes all settings enabled by 'Apply Suggested Settings'.
        """
        # Tuple lists aren't pretty but guarentee OrderedDict in older Cura versions
        presets = [(
            "pressure", [
                ("klipper_tuning_tower_command", "SET_PRESSURE_ADVANCE"),
                ("klipper_tuning_tower_parameter", "ADVANCE"),
                ("klipper_tuning_tower_method", "factor"),
                ("klipper_tuning_tower_start", 0),
                ("klipper_tuning_tower_skip", 0),
                ("klipper_tuning_tower_factor", 0),
                ("klipper_tuning_tower_band", 0),
                ("klipper_velocity_limits_enable", True),
                ("klipper_velocity_limit", 0),
                ("klipper_accel_limit", 500),
                ("klipper_accel_to_decel_limit", 0),
                ("klipper_corner_velocity_limit", 1.0),
                ("klipper_pressure_advance_enable", True),
                ("klipper_pressure_advance_factor", 0),
                ("acceleration_enabled", False)
            ]),(
            "accel", [
                ("klipper_tuning_tower_command", "SET_VELOCITY_LIMIT"),
                ("klipper_tuning_tower_parameter", "ACCEL"),
                ("klipper_tuning_tower_method", "step"),
                ("klipper_tuning_tower_start", 1500),
                ("klipper_tuning_tower_skip", 0),
                ("klipper_tuning_tower_step_delta", 500),
                ("klipper_tuning_tower_step_height", 5),
                ("klipper_velocity_limits_enable", True),
                ("klipper_velocity_limit", 0),
                ("klipper_accel_limit", 0),
                ("klipper_accel_to_decel_limit", 7000),
                ("klipper_corner_velocity_limit", 1.0),
                ("klipper_pressure_advance_enable", True),
                ("klipper_pressure_advance_factor", 0),
                ("klipper_input_shaper_enable", True),
                ("klipper_shaper_freq_x", 0),
                ("klipper_shaper_freq_y", 0),
                ("acceleration_enabled", False)
            ])
            ## Next Preset:
        ]

        presets = OrderedDict(presets) # Convert and preserve setting order
        preset_dict = OrderedDict() # type: OrderedDict[str, Any]

        for preset in presets:

            if preset == new_preset:
                preset_dict.update(presets[preset]) 

                if not override: # Set only tuning tower settings
                    preset_dict = {k: v for k, v in preset_dict.items() if k.startswith("klipper_tuning")}

        return preset_dict


    # Dict order must be preserved
    __pressure_advance_setting_key = {
        "_FACTORS": "klipper_pressure_advance_factor", ## [0-3] Parent settings
        "_WALLS": "klipper_pressure_advance_factor_wall",
        "_SUPPORTS": "klipper_pressure_advance_factor_support",
        "LAYER_0": "klipper_pressure_advance_factor_layer_0",
        "WALL-OUTER": "klipper_pressure_advance_factor_wall_0", ## [4-7] Gcode mesh features
        "WALL-INNER": "klipper_pressure_advance_factor_wall_x",
        "SKIN": "klipper_pressure_advance_factor_topbottom",
        "FILL": "klipper_pressure_advance_factor_infill",
        "SUPPORT": "klipper_pressure_advance_factor_support_infill", ## [8-11] Gcode non-mesh features
        "SUPPORT-INTERFACE": "klipper_pressure_advance_factor_support_interface",
        "PRIME-TOWER": "klipper_pressure_advance_factor_prime_tower",
        "SKIRT": "klipper_pressure_advance_factor_skirt_brim"
    }
    __velocity_limit_setting_key = {
        "velocity": "klipper_velocity_limit",
        "accel": "klipper_accel_limit",
        "accel_to_decel": "klipper_accel_to_decel_limit",
        "square_corner_velocity": "klipper_corner_velocity_limit"
    }
    __firmware_retraction_setting_key = {
        "retract_length": "klipper_retract_distance",
        "unretract_extra_length": "klipper_unretract_extra",
        "retract_speed": "klipper_retract_speed",
        "unretract_speed": "klipper_unretract_speed"
    }
    __input_shaper_setting_key = {
        "shaper_freq_x": "klipper_shaper_freq_x",
        "shaper_freq_y": "klipper_shaper_freq_y",
        "shaper_type_x": "klipper_shaper_type_x",
        "shaper_type_y": "klipper_shaper_type_y",
        "damping_ratio_x": "klipper_damping_ratio_x",
        "damping_ratio_y": "klipper_damping_ratio_y"
    }
    __tuning_tower_setting_key = {
        "tuning_method": "klipper_tuning_tower_method",
        "command": "klipper_tuning_tower_command",
        "parameter": "klipper_tuning_tower_parameter",
        "start": "klipper_tuning_tower_start",
        "skip": "klipper_tuning_tower_skip",
        "factor": "klipper_tuning_tower_factor",
        "band": "klipper_tuning_tower_band",
        "step_delta": "klipper_tuning_tower_step_delta",
        "step_height": "klipper_tuning_tower_step_height"
    }
