# VerityAI website template ZIP format

Website templates uploaded in the operator console are data packages, not deployable code. This boundary prevents an uploaded theme from executing scripts or server code across customer tenants.

## Package layout

Create a ZIP file containing exactly:

```text
template.json
README.md        (optional)
```

The ZIP is limited to 5 MB compressed, 10 MB expanded and 20 entries. Nested paths, symlinks, encrypted entries and any other files are rejected.

## `template.json`

```json
{
  "key": "my-business-v1",
  "name": "My Business",
  "category": "Business",
  "description": "A concise description shown in the customer catalogue.",
  "definition": {
    "schema_version": 1,
    "site": {
      "title": "{{business_name}}",
      "description": "A trusted {{business_nature}} organisation.",
      "language": "en"
    },
    "brand": {
      "primary_color": "#2457d6",
      "secondary_color": "#0f766e",
      "background_color": "#ffffff",
      "text_color": "#172033"
    },
    "navigation": [{"label": "Home", "page_slug": "home"}],
    "pages": [{
      "slug": "home",
      "title": "Home",
      "description": "Welcome",
      "sections": [{
        "id": "hero-1",
        "type": "hero",
        "heading": "Welcome to {{business_name}}",
        "body": "Explain the value of this organisation clearly.",
        "primary_action": {"label": "Contact us", "url": "/contact"}
      }]
    }],
    "integrations": {
      "widget_enabled": true,
      "whatsapp_enabled": false,
      "crm_enabled": true
    }
  }
}
```

Supported placeholders are `{{business_name}}` and `{{business_nature}}`. Definitions support the structured section types enforced by `websites/definitions.py`; arbitrary HTML, JavaScript, data URLs, event handlers and unknown fields are rejected.

The original ZIP is retained as a private, checksum-addressed operator record. Every customer project receives its own immutable validated definition version, so changing or deactivating a catalogue template never modifies an existing customer site.
