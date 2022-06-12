# Copyright (c) 2022 J.Jarrard / JJFX
# The KlipperSettingsPlugin is released under the terms of the AGPLv3 or higher.

from . import KlipperSettingsPlugin


def getMetaData():
    return {}

def register(app):
    return {"extension": KlipperSettingsPlugin.KlipperSettingsPlugin()}
