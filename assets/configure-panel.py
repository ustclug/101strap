#!/usr/bin/env python3
"""Remove the unused power-manager plugin and its panel references."""

import sys
import xml.etree.ElementTree as ET

panel_path = sys.argv[1]
tree = ET.parse(panel_path)
plugins = tree.getroot().find("./property[@name='plugins']")
if plugins is None:
    raise SystemExit("Xfce panel configuration has no plugins property")

for plugin in list(plugins):
    if plugin.get("value") != "power-manager-plugin":
        continue
    plugin_id = plugin.attrib["name"].removeprefix("plugin-")
    for references in tree.findall(".//property[@name='plugin-ids']"):
        for reference in list(references):
            if reference.tag == "value" and reference.get("value") == plugin_id:
                references.remove(reference)
    plugins.remove(plugin)

tree.write(panel_path, encoding="UTF-8", xml_declaration=True)
