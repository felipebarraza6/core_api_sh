from django import forms
from django.core.exceptions import ValidationError
import json
from .models import TelemetryProvider

class TelemetryProviderForm(forms.ModelForm):
    class Meta:
        model = TelemetryProvider
        fields = '__all__'
        widgets = {
            'auth_config': forms.Textarea(attrs={
                'rows': 12,
                'style': 'font-family: "Fira Code", "Roboto Mono", monospace; background-color: #1e1e1e; color: #a9b7c6; width: 100%; border: 1px solid #444;',
                'placeholder': '{\n    "type": "bearer",\n    "token": "..."\n}',
                'onblur': 'try { const obj = JSON.parse(this.value); this.value = JSON.stringify(obj, null, 4); this.style.borderColor = "#444"; } catch(e) { this.style.borderColor = "#ff4444"; }'
            }),
            'response_mapping': forms.Textarea(attrs={
                'rows': 15,
                'style': 'font-family: "Fira Code", "Roboto Mono", monospace; background-color: #1e1e1e; color: #9876aa; width: 100%; border: 1px solid #444;',
                'onblur': 'try { const obj = JSON.parse(this.value); this.value = JSON.stringify(obj, null, 4); this.style.borderColor = "#444"; } catch(e) { this.style.borderColor = "#ff4444"; }'
            }),
            'endpoint_template': forms.TextInput(attrs={
                'style': 'font-family: monospace; width: 100%; font-size: 1.1em; background-color: #f0f4f8; border: 1px solid #ccc;'
            }),
            'request_template': forms.Textarea(attrs={
                'rows': 10,
                'style': 'font-family: "Fira Code", monospace; background-color: #1e1e1e; color: #6a8759; width: 100%; border: 1px solid #444;',
                'onblur': 'try { const obj = JSON.parse(this.value); this.value = JSON.stringify(obj, null, 4); this.style.borderColor = "#444"; } catch(e) { this.style.borderColor = "#ff4444"; }'
            }),
        }
        help_texts = {
            'auth_config': "JSON Configuration. <strong>On Blur (click outside), content will auto-format. Red border indicates invalid JSON.</strong><br>Examples: <code>{\"header\": \"Authorization\", \"prefix\": \"Bearer \"}</code>",
            'response_mapping': "Map internal variables to JSON paths. <br>Ex: <code>{\"pc\": \"results.pressure.0.val\", \"descarga\": \"data.flow\"}</code>"
        }

    def clean(self):
        cleaned_data = super().clean()
        auth_method = cleaned_data.get('auth_method')
        auth_config = cleaned_data.get('auth_config')
        
        # 1. Validation for Authentication Config
        if auth_method == 'api_key':
            if not auth_config.get('header') and not auth_config.get('query_param'):
                self.add_error('auth_config', "For 'api_key', you must specify 'header' or 'query_param' key.")
        
        elif auth_method == 'bearer':
            # Check for required fields for Login flow
            required_keys = ['login_url', 'username', 'password', 'token_key']
            missing = [key for key in required_keys if key not in auth_config]
            if missing:
                self.add_error('auth_config', f"For 'bearer' (login flow), missing keys: {', '.join(missing)}")

        elif auth_method == 'basic':
            if 'username' not in auth_config or 'password' not in auth_config:
                self.add_error('auth_config', "For 'basic' auth, 'username' and 'password' are required.")

        # 2. Validation for Templates
        endpoint = cleaned_data.get('endpoint_template')
        if endpoint and '{' in endpoint and '}' not in endpoint:
             self.add_error('endpoint_template', "Invalid placeholder syntax. Use {param}.")
        
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pretty Print JSON fields in the text area for better editing
        json_fields = ['auth_config', 'endpoint_template', 'request_template', 'response_mapping']
        
        if self.instance.pk:
            for field in json_fields:
                val = getattr(self.instance, field)
                if isinstance(val, dict) or isinstance(val, list):
                    # Setting initial value to pretty-printed string
                    # Note: Django's default JSONWidget might override this on save, but it helps on load.
                    self.initial[field] = json.dumps(val, indent=4)
