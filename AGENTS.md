# Agent Workflow Notes

## Packaging
- Always rebuild `QGIS-Plugin-Helper.zip` after making changes to plugin code or metadata.
- Use this command from repo root:

```bash
zip -r -q /tmp/QGIS-Plugin-Helper.zip qgis_plugin_helper -x '*.DS_Store' -x '__MACOSX/*' -x '*/__pycache__/*' -x '*.pyc' && mv /tmp/QGIS-Plugin-Helper.zip QGIS-Plugin-Helper.zip
```
