from __future__ import absolute_import, unicode_literals
from celery import task
from coursera_house.core.views import ControllerView
from coursera_house.core.models import Setting
from coursera_house import settings
import json
import requests
from django.http import HttpResponse, JsonResponse


def get_data():
    """Функция опрса датчиков"""
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
        return JsonResponse({'errors': 'Bad request'}, status=400)
    return res

def change_settings(change):
    """Функция изменения настроек"""
    url = settings.SMART_HOME_API_URL
    url_token = settings.SMART_HOME_ACCESS_TOKEN
    data_list = {}
    data_list['controllers'] = change
    data = json.dumps(data_list)
    headers = {'Authorization': f'Bearer {url_token}', 'Content-Type':'application/json'}
    request = requests.post(url=url, headers=headers, data=data)
    return request.json()

@task()
def smart_home_manager():
    """Функция проверки состояния Умного дома"""
    bedroom_db = Setting.objects.get(controller_name='bedroom_target_temperature').value
    hotwater_db = Setting.objects.get(controller_name='hot_water_target_temperature').value
    indicators = get_data()
    print(f'Первоначальные показания {indicators}')

    #1 Если есть протечка воды (leak_detector=true),
    # закрыть холодную (cold_water=false) и горячую (hot_water=false) воду и
    # отослать письмо в момент обнаружения.
    if indicators['leak_detector'] == True:
        change = []
        change.append({'name': 'cold_water', 'value': False})
        change.append({'name': 'hot_water', 'value': False})
        change_settings(change)
    elif indicators['leak_detector'] == False:
        change = []
        change.append({'name': 'hot_water', 'value': True})
        change.append({'name': 'cold_water', 'value': True})
        change_settings(change)
    #Обновили информацию с дачиков
    indicators = get_data()

    #2 Если холодная вода (cold_water) закрыта, немедленно выключить бойлер (boiler) и стиральную машину (washing_machine)
    # и ни при каких условиях не включать их, пока холодная вода не будет снова открыта.
    if indicators['cold_water'] == False:
        change = []
        change.append({'name': 'boiler', 'value': False})
        change.append({'name': 'washing_machine', 'value': 'off'})
    # Обновили информацию с дачиков
    indicators = get_data()

    #3 Если горячая вода имеет температуру (boiler_temperature) меньше чем hot_water_target_temperature - 10%,
    # нужно включить бойлер (boiler), и ждать пока она не достигнет температуры hot_water_target_temperature + 10%,
    # после чего в целях экономии энергии бойлер нужно отключить
    if indicators['boiler_temperature'] is not None and 10 < 100 - ((indicators['boiler_temperature']/hotwater_db)*100):
        if indicators['cold_water'] == True:
            change = []
            change.append({'name': 'boiler', 'value': True})
            change_settings(change)
    elif indicators['boiler_temperature'] is not None and 10 < 100 - ((hotwater_db/indicators['boiler_temperature'])*100):
        change = []
        change.append({'name': 'boiler', 'value': False})
        change_settings(change)

    #Если шторы частично открыты (curtains == “slightly_open”),
    # то они находятся на ручном управлении - это значит их состояние нельзя изменять автоматически ни при каких условиях.
    #Если на улице (outdoor_light) темнее 50, открыть шторы (curtains), но только если не горит лампа в спальне (bedroom_light).
    if indicators['outdoor_light'] < 50 and \
        indicators['curtains'] != 'slightly_open' and indicators['bedroom_light'] is False:
        change = []
        change.append({'name':'curtains', 'value':'open'})
        change_settings(change)
    #Если на улице (outdoor_light) светлее 50,
    # или горит свет в спальне (bedroom_light), закрыть шторы. Кроме случаев когда они на ручном управлении
    elif (indicators['outdoor_light'] > 50 or indicators['bedroom_light'] is True) and \
        indicators['curtains'] != 'slightly_open':
        change = []
        change.append({'name':'curtains', 'value':'open'})
        change_settings(change)
    indicators = get_data()

    #6Если обнаружен дым (smoke_detector),
    # немедленно выключить следующие приборы [air_conditioner, bedroom_light, bathroom_light, boiler, washing_machine],
    # и ни при каких условиях не включать их, пока дым не исчезнет.
    if indicators['smoke_detector'] is True:
        change = []
        change.append({'name':'air_conditioner', 'value': False})
        change.append({'name': 'bedroom_light', 'value': False})
        change.append({'name': 'bathroom_light', 'value': False})
        change.append({'name': 'boiler', 'value': False})
        change.append({'name': 'washing_machine', 'value': 'off'})
        change_settings(change)
    indicators = get_data()

    return indicators
