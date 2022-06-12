# KlipperSettingsPlugin v0.8.0 - Beta
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
# v0.8.0  | Tested up to Cura version 5.0
#         | Pressure Advance Settings (v1.5)
#         | Tuning Tower Settings  (v1.0)
#         | Velocity Limits Settings (v1.0)
#

import os.path, json
from collections import OrderedDict # Ensure order of imported settings in all versions
from typing import List, Optional, Any, Dict, TYPE_CHECKING

from cura.CuraApplication import CuraApplication

from UM.Extension import Extension
from UM.Logger import Logger
from UM.Version import Version # Some features are disabled for older versions
from UM.Resources import Resources # Add local path to plugin resources dir

from UM.Settings.SettingDefinition import SettingDefinition     # Create and register setting definitions
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.ContainerRegistry import ContainerRegistry

from UM.Message import Message # Display messages to user
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator # To parse per-object settings

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("KlipperSettingsPlugin")

if TYPE_CHECKING:
    from UM.OutputDevice.OutputDevice import OutputDevice

class KlipperSettingsPlugin(Extension):
    def __init__(self) -> None:
        super().__init__()

        self._application = CuraApplication.getInstance()

        self._i18n_catalog = None  # type: Optional[i18nCatalog]

        self._settings_dict = {}   # type: Dict[str, Any]
        
        self._category_key = "klipper_settings"
        self._category_dict = {
            "label": "Klipper Settings",
            "description": "Features and Settings Specific to Klipper Firmware",
            "type": "category",
            "icon": "Quick"     # Temp - Need solution for loading the custom icon without creating theme
            #"icon": "Klipper"
        }

        try:
            with open(os.path.join(os.path.dirname(__file__), "klipper_settings.def.json"), encoding = "utf-8") as f:
                self._settings_dict = json.load(f, object_pairs_hook = OrderedDict)
        except:
            Logger.logException('e', "Could not load klipper settings definition")
            return

        # Local resource path for scripts and other elements (future use)
        Resources.addSearchPath(os.path.join(os.path.dirname(__file__), "resources"))

        ContainerRegistry.getInstance().containerLoadComplete.connect(self._onContainerLoadComplete)
        self._application.engineCreatedSignal.connect(self._fixCategoryVisibility) # Check visibility at start
        self._application.getPreferences().preferenceChanged.connect(self._fixCategoryVisibility)

        self._application.getOutputDeviceManager().writeStarted.connect(self._filterGcode)


    def _onContainerLoadComplete(self, container_id: str) -> None:
        # -----------------------------------------------------------------------------------------
        #  Parse loaded containers until definition container is found.
        #  Register new 'Klipper Settings' category and add imported settings to it.
        # -----------------------------------------------------------------------------------------
        if not ContainerRegistry.getInstance().isLoaded(container_id):
            return # Skip containers that could not be loaded to avoid infinite findContainers() loop

        try:
            container = ContainerRegistry.getInstance().findContainers(id = container_id)[0]
        except IndexError:
            return # Container no longer exists

        if not isinstance(container, DefinitionContainer) or container.getMetaDataEntry("type") == "extruder":
            return # Skip non-definition containers

        # Create new settings category
        klipper_category = SettingDefinition(self._category_key, container, None, self._i18n_catalog)
        klipper_category.deserialize(self._category_dict)

        container.addDefinition(klipper_category) # Register category setting definition

        try: # Make sure new category actually exists
            klipper_category = container.findDefinitions(key=self._category_key)[0]
        except IndexError:
            Logger.log('e', "Could not find new settings category: '%s'", self._category_key)
            return

        # Add all setting definitions to new category
        for setting_key in self._settings_dict.keys():
            setting_definition = SettingDefinition(setting_key, container, klipper_category, self._i18n_catalog)
            setting_definition.deserialize(self._settings_dict[setting_key])

            klipper_category._children.append(setting_definition)
            container._definition_cache[setting_key] = setting_definition
            # Check for setting children
            if setting_definition.children:
                self._updateAddedChildren(container, setting_definition)

        container._updateRelations(klipper_category) # Update relations of all category settings

    def _updateAddedChildren(self, container: DefinitionContainer, setting_definition: SettingDefinition) -> None:
        #  Update definition cache for setting definition children
        for child in setting_definition.children:
            container._definition_cache[child.key] = child

            if child.children:
                self._updateAddedChildren(container, child)

    def _fixCategoryVisibility(self, preference: str = "general/visible_settings") -> None:
        # -----------------------------------------------------------------------------------------
        #  Ensure new category is in visibile settings at start and when visible settings change.
        # -----------------------------------------------------------------------------------------
        if preference != "general/visible_settings":
            return

        preferences = self._application.getPreferences()
        visible_settings = preferences.getValue(preference)

        if not visible_settings:
            return # List could be empty and is fixed once user adds a visibile setting

        if self._category_key not in visible_settings:
            visible_settings += ";%s" % self._category_key

            preferences.setValue(preference, visible_settings) # Add category to visible settings


    def _filterGcode(self, output_device: "OutputDevice") -> None:
        # -----------------------------------------------------------------------------------------
        #  Check for enabled settings then insert commands for each at start of gcode.
        #  Parse gcode to insert extruder and/or per-object Pressure Advance settings into gcode.
        # -----------------------------------------------------------------------------------------
        scene = self._application.getController().getScene()
        global_stack = self._application.getGlobalContainerStack()
        extruder_manager = self._application.getExtruderManager()
        used_extruder_stacks = self._application.getExtruderManager().getUsedExtruderStacks()

        if not global_stack or not used_extruder_stacks:
            return

        # Disable per-object settings for older Cura versions
        version = Version(self._application.getVersion())
        support_per_object_settings = version >= Version("4.7.0")

        # Retrieve state of klipper setting controls (bool)
        pressure_advance_enabled = global_stack.getProperty("klipper_pressure_advance_enable", "value")
        velocity_limits_enabled = global_stack.getProperty("klipper_velocity_limits_enable", "value")
        tuning_tower_enabled = global_stack.getProperty("klipper_tuning_tower_enable", "value")

        gcode_dict = getattr(scene, "gcode_dict", {})
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

            # KLIPPER TUNING TOWER COMMAND --------------------------------------------------------
            if not tuning_tower_enabled:
                Logger.log('d', "Klipper Tuning Tower is Disabled")
            else:
                tower_settings = {} # type: Dict[str, Any]
                # Parse tuning tower settings to pass to function
                for tower_key, tower_setting in self.__tuning_tower_setting_key.items():
                    tower_settings[tower_key] = global_stack.getProperty(tower_setting, "value")

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeTuningTower(tower_settings) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('e', "Tuning tower command could not be processed")
                    return # Stop on error

            # KLIPPER VELOCITY LIMITS COMMAND -----------------------------------------------------
            if not velocity_limits_enabled:
                Logger.log('d', "Klipper Velocity Limit Control is Disabled")
            else:
                velocity_limits = {} # type: Dict[str, int]
                # Parse velocity settings to pass to function
                for limit_key, limit_setting in self.__velocity_limit_setting_key.items():
                    velocity_limits[limit_key] = global_stack.getProperty(limit_setting, "value")

                try: # Add returned command to start of gcode
                    gcode_list[1] = gcode_list[1] + (
                        self._gcodeVelocityLimits(velocity_limits) + ";KlipperSettingsPlugin\n")

                    dict_changed = True

                except TypeError:
                    Logger.log('d', "Klipper velocity limits were not changed")

            # KLIPPER PRESSURE ADVANCE COMMAND ----------------------------------------------------
            if not pressure_advance_enabled:
                Logger.log('d', "Klipper Pressure Advance Control is Disabled")
                break

            # Extruder Dictionaries
            apply_factor_per_feature = {}  # type: Dict[int, bool]
            current_advance_factors = {}   # type: Dict[int, float]
            per_extruder_settings = {}     # type: Dict[(int,str), float]
            # Mesh Object Dictionaries
            apply_factor_per_mesh = {}     # type: Dict[str, bool]
            per_mesh_settings = {}         # type: Dict[(str,str), float]

            non_mesh_features = [*self.__gcode_type_to_setting_key][8:] # SUPPORT, SKIRT, etc.
            parent_setting_key = "klipper_pressure_advance_factor" # Primary setting

            ### Get settings for all active extruders
            for extruder_stack in used_extruder_stacks:
                extruder_nr = int(extruder_stack.getProperty("extruder_nr", "value"))
                pressure_advance_factor = extruder_stack.getProperty(parent_setting_key, "value")
                current_advance_factors[extruder_nr] = pressure_advance_factor

                try: # Add primary value of each extruder to start of gcode
                    gcode_list[1] = gcode_list[1] + gcode_cmd_pattern % (
                        pressure_advance_factor, str(extruder_nr).strip('0')) + "\n"

                    dict_changed = True

                except TypeError:
                    Logger.log('e', "Invalid pressure advance value: '%s'", pressure_advance_factor)
                    return

                # Get all feature settings for each extruder
                for feature_key, setting_key in self.__gcode_type_to_setting_key.items():
                    per_extruder_settings[(extruder_nr, feature_key)] = extruder_stack.getProperty(setting_key, "value")

                    # Check for unique feature settings
                    if per_extruder_settings[(extruder_nr, feature_key)] != pressure_advance_factor:
                        apply_factor_per_feature[extruder_nr] = True # Flag to process gcode


            ### Get settings for all printable mesh objects that are not support
            nodes = [node for node in DepthFirstIterator(scene.getRoot())
                     if node.isSelectable()and not node.callDecoration("isNonThumbnailVisibleMesh")]
            if not nodes:
                Logger.log('w', "No valid objects in scene to process")
                return

            for node in nodes:
                if not support_per_object_settings:
                    Logger.log('d', "Per-object settings disabled for Cura version %s", version)
                    break # Use extruder values for older Cura versions

                mesh_name = node.getName() # Filename of mesh with extension
                mesh_settings = node.callDecoration("getStack").getTop()
                extruder_nr = int(node.callDecoration("getActiveExtruderPosition"))

                # Get all feature settings for each mesh object
                for feature_key, setting_key in self.__gcode_type_to_setting_key.items():
                    if mesh_settings.getInstance(setting_key) is not None:
                        mesh_setting_value = mesh_settings.getInstance(setting_key).value
                    else:
                        # Use extruder value if no per object setting is defined
                        if (mesh_name, feature_key) not in per_mesh_settings:
                            per_mesh_settings[(mesh_name, feature_key)] = per_extruder_settings[(extruder_nr, feature_key)]

                        continue

                    # Save the children!
                    for feature in (
                        [*self.__gcode_type_to_setting_key][4:8] if feature_key == "_FACTORS"
                            else ['WALL-OUTER', 'WALL-INNER'] if feature_key == "_WALLS"
                            else ['SUPPORT', 'SUPPORT-INTERFACE'] if feature_key == "_SUPPORTS"
                            else [feature_key]):

                        if mesh_setting_value != per_extruder_settings[(extruder_nr,feature)]:
                            if mesh_setting_value != per_mesh_settings.get((mesh_name,feature)):
                                apply_factor_per_mesh[(mesh_name,feature)] = True
                                per_mesh_settings[(mesh_name,feature)] = mesh_setting_value

                                apply_factor_per_feature[extruder_nr] = True # Flag to process gcode

            ### Post-process gcode loop
            if any(apply_factor_per_feature.values()):
                active_extruder_list = [*apply_factor_per_feature] # type: List[int]
                active_mesh_list = [*zip(*per_mesh_settings)][0]   # type: List[str]
                # Loop start parameters
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


    def _gcodeTuningTower(self, tower_settings: Dict[str, str]) -> str:
        # -----------------------------------------------------------------------------------------
        #  Parse enabled tuning tower settings to return as single gcode command
        # -----------------------------------------------------------------------------------------
        tower_settings = {key: i for key, i in tower_settings.items() if not (
            key in ['skip', 'band'] and i == 0)} # Remove opt. values set to 0

        # Strip any leading/trailing quotes and other characters
        for index, cmd in enumerate(['command', 'parameter']):
            tower_settings[cmd] = tower_settings[cmd].strip('.,;="\'')
            # Validate reasonable string length and that parameter is one word
            if len(tower_settings[cmd]) > 50 or (index == 1 and len(tower_settings[cmd].split()) > 1):
                self.showMessage(
                    "<b>Command</b> and/or <b>Parameter</b> settings are too long!<br />",
                    "ERROR", "Klipper Tuning Tower Disabled", 30)
                return # TypeError

        # Add single quotes if command has multiple words
        if len(tower_settings['command'].split()) > 1:
            tower_settings['command'] = "'%s'" % tower_settings['command']

        gcode_command = "TUNING_TOWER "
        method = tower_settings.pop('tuning_method') # Get method and remove from dict

        for tower_key, tower_value in tower_settings.items():
            if method == "factor" and tower_key in ['step_delta', 'step_height']:
                continue
            if method == "step" and tower_key in ['factor', 'band']:
                continue

            gcode_command += "%s=%s " % (tower_key.upper(), tower_value)
        
        # Remind user tuning tower sequence is active
        self.showMessage(
            "Tuning tower sequence will affect <em><b>all objects</b></em> on the build plate.",
            "NEUTRAL", "Klipper Tuning Tower Enabled")

        return gcode_command

    def _gcodeVelocityLimits(self, velocity_limits: Dict[str, int]) -> str:
        # -----------------------------------------------------------------------------------------
        #  Parse enabled velocity settings to return as single gcode command
        # -----------------------------------------------------------------------------------------
        if velocity_limits['square_corner_velocity'] == 0:
            self.showMessage(
                "<b>WARNING:</b> Square Corner Velocity is set to 0<br /><br /> <em>To disable control, value must be set to -1</em>",
                "WARNING", "Klipper Velocity Limits", 30)

        # Remove disabled settings
        velocity_limits = {key: d for key, d in velocity_limits.items() if (
            key != "square_corner_velocity" and d > 0) or (
            key == "square_corner_velocity" and d >= 0)}

        if any(value >= 0 for value in velocity_limits.values()):
            gcode_command = "SET_VELOCITY_LIMIT "

            for limit_key, limit_value in velocity_limits.items():
                gcode_command += "%s=%d " % (limit_key.upper(), limit_value) # Create gcode command

            return gcode_command # TypeError if no return

    def showMessage(self, text: str, msg_type = 1, msg_title: str="Klipper Settings", msg_time: int = 15) -> None:
        # -----------------------------------------------------------------------------------------
        #  Helper function to display messages to user
        # -----------------------------------------------------------------------------------------
        if not isinstance(msg_type, int):
            msg_type = (
                0 if msg_type == "POSITIVE" else
                1 if msg_type == "NEUTRAL" else
                2 if msg_type == "WARNING" else 3 
            )
        display_message = Message(text,
            lifetime = msg_time,
            title = "<font size='+1'>%s</font>" % msg_title,
            message_type = msg_type)

        display_message.show() # Display message box


    # Dict order must be preserved!
    __gcode_type_to_setting_key = {
        "_FACTORS": "klipper_pressure_advance_factor", # [0-3] Non-feature parent settings
        "_WALLS": "klipper_pressure_advance_factor_wall",
        "_SUPPORTS": "klipper_pressure_advance_factor_support",
        "LAYER_0": "klipper_pressure_advance_factor_layer_0",
        "WALL-OUTER": "klipper_pressure_advance_factor_wall_0", # [4-7] Gcode mesh features
        "WALL-INNER": "klipper_pressure_advance_factor_wall_x",
        "SKIN": "klipper_pressure_advance_factor_topbottom",
        "FILL": "klipper_pressure_advance_factor_infill",
        "SUPPORT": "klipper_pressure_advance_factor_support_infill", # [8-11] Gcode non-mesh features
        "SUPPORT-INTERFACE": "klipper_pressure_advance_factor_support_interface",
        "PRIME-TOWER": "klipper_pressure_advance_factor_prime_tower",
        "SKIRT": "klipper_pressure_advance_factor_skirt_brim"
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
    __velocity_limit_setting_key = {
        "velocity": "klipper_velocity_limit",
        "accel": "klipper_accel_limit",
        "accel_to_decel": "klipper_accel_to_decel_limit",
        "square_corner_velocity": "klipper_corner_velocity_limit"
    }

