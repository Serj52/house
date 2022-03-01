from django.urls import reverse_lazy
from django.views.generic import FormView
import requests
from .models import Setting
from .form import ControllerForm
import json
from django.http import JsonResponse
from coursera_house import settings


class ControllerView(FormView):
    form_class = ControllerForm
    template_name = 'core/control.html'
    success_url = reverse_lazy('form')

    def get_context_data(self, **kwargs):
        """Polling sensors"""
        context = super(ControllerView, self).get_context_data()
        context['data'] = self.get_initial()
        return context

    def get_initial(self):
        """Data of sensors"""
        url = settings.SMART_HOME_API_URL
        url_token = settings.SMART_HOME_ACCESS_TOKEN
        headers = {'Authorization': f'Bearer {url_token}'}
        request = requests.get(url=url, headers=headers)
        try:
            if request.json()['status'] == 'ok':
                res = {}
                for i in request.json()['data']:
                    res[i.get("name")] = i.get("value")
                return res
            elif request.json()['status'] == 'access_denied':
                return JsonResponse({'errors': 'Bad autorization'}, status=401)
        except json.JSONDecoder:
            return JsonResponse({'errors': 'Bad request'}, status=502)

    def post(self, request, *args, **kwargs):
        """Data processing from a form"""
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return JsonResponse({'errors': 'Bad validation'}, status=400)

    def form_valid(self, form):
        """Recording to db"""

        if form.cleaned_data['bedroom_target_temperature']:
            bedroom_set = form.cleaned_data['bedroom_target_temperature']
            # If the database contains the record, then update the values
            if Setting.objects.filter(controller_name='bedroom_target_temperature').exists():
                bedroom_db = Setting.objects.get(controller_name='bedroom_target_temperature').value
                if bedroom_set != bedroom_db:
                    # Update the values
                    Setting.objects.filter(controller_name='bedroom_target_temperature').update(value=bedroom_set)
            # if the database does not contain the record, then create
            else:
                s = Setting.objects.create(controller_name='bedroom_target_temperature', value=bedroom_set)
                s.save()

        if form.cleaned_data['hot_water_target_temperature']:
            hotwater_set = form.cleaned_data['hot_water_target_temperature']
            # If the database contains the record, then update the values
            if Setting.objects.filter(controller_name='hot_water_target_temperature').exists():
                hotwater_db = Setting.objects.get(controller_name='hot_water_target_temperature').value
                if hotwater_set != hotwater_db:
                    # Update the values
                    Setting.objects.filter(controller_name='hot_water_target_temperature').update(value=hotwater_set)
            # if the database does not contain the record, then create
            else:
                Setting.objects.create(controller_name='hot_water_target_temperature', value=hotwater_set)

        if form.cleaned_data['bedroom_light']:
            bedroom_light_set = form.cleaned_data['bedroom_light']
            # If the database contains the record, then update the values
            if Setting.objects.filter(controller_name='bedroom_light').exists():
                bedroom_light_db = Setting.objects.get(controller_name='bedroom_light').value
                if bedroom_light_set != bedroom_light_db:
                    # Update the values
                    Setting.objects.filter(controller_name='bedroom_light').update(value=bedroom_light_set)
            # if the database does not contain the record, then create
            else:
                Setting.objects.create(controller_name='bedroom_light', value=bedroom_light_set)

        if form.cleaned_data['bathroom_light']:
            bathroom_light_set = form.cleaned_data['bathroom_light']
            # If the database contains the record, then update the values
            if Setting.objects.filter(controller_name='bathroom_light').exists():
                bathroom_light_db = Setting.objects.get(controller_name='bathroom_light').value
                if bathroom_light_set != bathroom_light_db:
                    # Update the values
                    Setting.objects.filter(controller_name='bathroom_light').update(value=bathroom_light_set)
            # if the database does not contain the record, then create 
            else:
                Setting.objects.create(controller_name='bathroom_light', value=bathroom_light_set)
        return super(ControllerView, self).form_valid(form)
