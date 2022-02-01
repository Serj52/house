from django.urls import reverse_lazy
from django.views.generic import FormView
import requests
from .models import Setting
from .form import ControllerForm
from jsonschema import validate
from jsonschema.exceptions import ValidationError
import pdb
import json
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from coursera_house import settings

class ControllerView(FormView):
    form_class = ControllerForm
    template_name = 'core/control.html'
    success_url = reverse_lazy('form')

    def get_context_data(self, **kwargs):
        context = super(ControllerView, self).get_context_data()
        context['data'] = self.get_initial()
        return context

    def get_initial(self):
        # url = 'http://smarthome.webpython.graders.eldf.ru/api/user.controller'
        # headers = {'Authorization': 'Bearer a9706fa6689509aca59103cd6713e6b4df89ea09caf562aa4d8bfb78b276d9a4'}
        url = settings.SMART_HOME_API_URL
        url_token = settings.SMART_HOME_ACCESS_TOKEN
        headers = {'Authorization': f'Bearer {url_token}'}
        request = requests.get(url=url, headers=headers)
        res = {}
        try:
            if request.json()['status'] == 'ok':
                for i in request.json()['data']:
                    res[i.get("name")] = i.get("value")
            elif request.json()['status'] == 'access_denied':
                return JsonResponse({'errors':'Bad autorization'}, status=401)
        except json.JSONDecoder:
            return JsonResponse({'errors':'Bad request'}, status=400)
        return res

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            self.form_valid(form)
            return redirect('form')
        else:
            return JsonResponse({'errors': 'Bad validation'}, status=400)

    def form_valid(self, form):
        bedroom_set = form.cleaned_data['bedroom_target_temperature']
        hotwater_set = form.cleaned_data['hot_water_target_temperature']
        bedroom_db = Setting.objects.get(controller_name='bedroom_target_temperature').value
        hotwater_db = Setting.objects.get(controller_name='hot_water_target_temperature').value
        if bedroom_set != bedroom_db and hotwater_set != hotwater_db:
            # Обновляем данные
            Setting.objects.filter(controller_name='bedroom_target_temperature').update(value=bedroom_set)
            # Обновляем данные
            Setting.objects.filter(controller_name='hot_water_target_temperature').update(value=hotwater_set)
        return super(ControllerView, self).form_valid(form)
