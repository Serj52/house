from __future__ import absolute_import, unicode_literals
import json
import requests
from django.http import JsonResponse
from django.core.mail import send_mail
from celery import task
from coursera_house.core.models import Setting
from coursera_house import settings


def get_data():
    """Polling sensors"""
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
            return JsonResponse({'errors': 'Bad autorization'}, status=401)
    except json.JSONDecoder:
        return JsonResponse({'errors': 'Bad request'}, status=502)
    return res


def change_settings(change):
    """Change settings"""
    url = settings.SMART_HOME_API_URL
    url_token = settings.SMART_HOME_ACCESS_TOKEN
    data_list = {}
    data_list['controllers'] = change
    data = json.dumps(data_list)
    headers = {'Authorization': f'Bearer {url_token}', 'Content-Type': 'application/json'}
    request = requests.post(url=url, headers=headers, data=data)
    print('Данные отправлены')
    return request.json()


@task()
def smart_home_manager():
    """Reaction on the sensors"""
    bedroom_db = Setting.objects.get(controller_name='bedroom_target_temperature').value
    hotwater_db = Setting.objects.get(controller_name='hot_water_target_temperature').value
    indicators = get_data()
    # List changes
    change = []

    # If the hot water has temperature (boiler_temperature) lower
    # than the hot_water_target_temperature - 10%,
    # then the boiler must be turn on (boiler)
    if indicators['boiler_temperature'] < hotwater_db and 10 >= (
            (hotwater_db / indicators['boiler_temperature']) - 1) * 100:
        if indicators['boiler'] is False and indicators['smoke_detector'] is False and indicators[
            'cold_water'] is True and indicators['leak_detector'] is False:
            change.append({'name': 'boiler', 'value': True})
    # Wait until the boiler_temperature will be equal the hot_water_target_temperature + 10%,
    # and then turn off the boiler
    if indicators['boiler_temperature'] > hotwater_db and 10 <= (
            (indicators['boiler_temperature'] / hotwater_db) - 1) * 100:
        if indicators['boiler'] is True and indicators['smoke_detector'] is False and indicators[
            'cold_water'] is True and indicators['leak_detector'] is False:
            change.append({'name': 'boiler', 'value': False})

    if Setting.objects.filter(controller_name='bedroom_light').exists():
        bedroom_light_db = Setting.objects.get(controller_name='bedroom_light').value
        if bedroom_light_db != indicators['bedroom_light'] and indicators['smoke_detector'] is False:
            change.append({'name': 'bedroom_light', 'value': bedroom_light_db})

    if Setting.objects.filter(controller_name='bathroom_light').exists():
        bathroom_light_db = Setting.objects.get(controller_name='bathroom_light').value
        if bathroom_light_db != indicators['bathroom_light'] and indicators['smoke_detector'] is False:
            change.append({'name': 'bathroom_light', 'value': bathroom_light_db})

    # If curtains == “slightly_open”, then their condition cannot be change.
    # If outdoor darker (outdoor_light < 50) than 50, then
    # open the curtains (curtains), but only if the light is off.
    if indicators['outdoor_light'] < 50 and indicators['bedroom_light'] is False:
        if indicators['curtains'] == 'close' or indicators['curtains'] != 'slightly_open':
            change.append({'name': 'curtains', 'value': 'open'})

    # If outdoor lighter (outdoor_light > 50) than 50 or
    # the bedroom_light is on in the bedroom, then curtains must be close.
    # Except when curtains == “slightly_open”
    if indicators['outdoor_light'] > 50 or indicators['bedroom_light'] is True:
        if indicators['curtains'] == 'open' and indicators['curtains'] != 'slightly_open':
            change.append({'name': 'curtains', 'value': 'close'})

    # If the bathroom_temperature is higher than bedroom_temperature_target + 10%
    #  - you must turn on air_conditioner
    if indicators['bedroom_temperature'] > bedroom_db and 10 <= (
            (indicators['bedroom_temperature'] / bedroom_db) - 1) * 100:
        if indicators['air_conditioner'] is False and indicators['smoke_detector'] is False:
            change.append({'name': 'air_conditioner', 'value': True})

    # If the bathroom_temperature will be lower than bedroom_target_temperature - 10%,
    # than turn off air_conditioner
    if bedroom_db > indicators['bedroom_temperature'] and 10 <= (
            (bedroom_db / indicators['bedroom_temperature'] - 1) * 100) or indicators['bedroom_temperature'] == 16:
        if indicators['air_conditioner'] is True and indicators['smoke_detector'] is False:
            change.append({'name': 'air_conditioner', 'value': False})

    # If leak_detector is true,
    # you will be cold_water=false and hot_water=false and
    # send warning mail
    if indicators['leak_detector'] is True:
        if indicators['cold_water'] is True:
            change.append({'name': 'cold_water', 'value': False})
        if indicators['hot_water'] is True:
            change.append({'name': 'hot_water', 'value': False})
        send_mail('Warning', 'leak_detector worked',
                  '@mail.ru', [settings.EMAIL_RECEPIENT])

    # If smoke_detector is true,
    # you must turn off the following devices:
    # [air_conditioner, bedroom_light, bathroom_light, boiler, washing_machine],
    # and you must not turn on them until smoke_detector is true.
    if indicators['smoke_detector'] is True:
        if indicators['air_conditioner'] is True:
            change.append({'name': 'air_conditioner', 'value': False})
        if indicators['bedroom_light'] is True:
            change.append({'name': 'bedroom_light', 'value': False})
        if indicators['bathroom_light'] is True:
            change.append({'name': 'bathroom_light', 'value': False})
        if indicators['boiler'] is True:
            change.append({'name': 'boiler', 'value': False})
        if indicators['washing_machine'] == 'on':
            change.append({'name': 'washing_machine', 'value': 'off'})

    if indicators['washing_machine'] == 'broken':
        change.append({'name': 'washing_machine', 'value': 'off'})

    if indicators['bedroom_presence'] is True or indicators['bedroom_motion'] is True:
        if indicators['bedroom_light'] is False:
            change.append({'name': 'bedroom_light', 'value': True})

    if indicators['bathroom_presence'] is True or indicators['bathroom_motion'] is True:
        if indicators['bathroom_light'] is False:
            change.append({'name': 'bathroom_light', 'value': True})

    if indicators['cold_water'] is False:
        if indicators['boiler'] is True:
            change.append({'name': 'boiler', 'value': False})
        if indicators['washing_machine'] == 'on':
            change.append({'name': 'washing_machine', 'value': 'off'})

    #Send changes if they are
    if len(change) > 0:
        change_settings(change)
