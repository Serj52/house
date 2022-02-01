from django import forms
import pdb

class ControllerForm(forms.Form):
    bedroom_target_temperature = forms.IntegerField(max_value=50, min_value=16)
    hot_water_target_temperature = forms.IntegerField(max_value=90, min_value=24)
    bedroom_light = forms.BooleanField()
    bathroom_light = forms.BooleanField()

    def clean(self):
        cleaned_data = super().clean()
        bedroom_temperature = self.data.get('bedroom_target_temperature')
        hot_temperature = self.data.get('hot_water_target_temperature')
        # pdb.set_trace()
        if bedroom_temperature.isdigit() and hot_temperature.isdigit():
            return cleaned_data
        raise forms.ValidationError('The field must be of type int.')



