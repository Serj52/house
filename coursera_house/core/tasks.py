from __future__ import absolute_import, unicode_literals
import json
import requests
from django.http import JsonResponse
from django.core.mail import send_mail
from celery import task
from coursera_house.core.models import Setting
from coursera_house import settings


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
        return JsonResponse({'errors': 'Bad request'}, status=502)
    return res


def change_settings(change):
    """Функция изменения настроек"""
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
    """Функция проверки состояния Умного дома"""
    bedroom_db = Setting.objects.get(controller_name='bedroom_target_temperature').value
    hotwater_db = Setting.objects.get(controller_name='hot_water_target_temperature').value
    indicators = get_data()
    # Лист изменений
    change = []

    # Если горячая вода имеет температуру (boiler_temperature) меньше чем hot_water_target_temperature - 10%,
    # нужно включить бойлер (boiler), и ждать пока она не достигнет температуры hot_water_target_temperature + 10%,
    # после чего в целях экономии энергии бойлер нужно отключить
    if indicators['boiler_temperature'] < hotwater_db and 10 >= (
            (hotwater_db / indicators['boiler_temperature']) - 1) * 100:
        if indicators['boiler'] is False and indicators['smoke_detector'] is False and indicators[
            'cold_water'] is True and indicators['leak_detector'] is False:
            change.append({'name': 'boiler', 'value': True})

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

    # Если шторы частично открыты (curtains == “slightly_open”),
    # то они находятся на ручном управлении - это значит их состояние нельзя изменять автоматически
    # ни при каких условиях.
    # Если на улице (outdoor_light) темнее 50, открыть шторы (curtains), но только если не горит лампа
    # в спальне (bedroom_light).
    if indicators['outdoor_light'] < 50 and indicators['bedroom_light'] is False:
        if indicators['curtains'] == 'close' or indicators['curtains'] != 'slightly_open':
            change.append({'name': 'curtains', 'value': 'open'})

    # Если на улице (outdoor_light) светлее 50,
    # или горит свет в спальне (bedroom_light), закрыть шторы.
    # Кроме случаев когда они на ручном управлении
    if indicators['outdoor_light'] > 50 or indicators['bedroom_light'] is True:
        if indicators['curtains'] == 'open' and indicators['curtains'] != 'slightly_open':
            change.append({'name': 'curtains', 'value': 'close'})

    # Если температура в спальне (bedroom_temperature) поднялась выше
    # bedroom_target_temperature + 10% - включить кондиционер
    # (air_conditioner),
    # и ждать пока температура не опустится ниже bedroom_target_temperature - 10%,
    # после чего кондиционер отключить.
    if indicators['bedroom_temperature'] > bedroom_db and 10 <= (
            (indicators['bedroom_temperature'] / bedroom_db) - 1) * 100:
        if indicators['air_conditioner'] is False and indicators['smoke_detector'] is False:
            change.append({'name': 'air_conditioner', 'value': True})

    if bedroom_db > indicators['bedroom_temperature'] and 10 <= (
            (bedroom_db / indicators['bedroom_temperature'] - 1) * 100) or indicators['bedroom_temperature'] == 16:
        if indicators['air_conditioner'] is True and indicators['smoke_detector'] is False:
            change.append({'name': 'air_conditioner', 'value': False})

    # Если есть протечка воды (leak_detector=true),
    # закрыть холодную (cold_water=false) и горячую (hot_water=false) воду и
    # отослать письмо в момент обнаружения.
    if indicators['leak_detector'] is True:
        if indicators['cold_water'] is True:
            change.append({'name': 'cold_water', 'value': False})
        if indicators['hot_water'] is True:
            change.append({'name': 'hot_water', 'value': False})
        send_mail('Warning', 'leak_detector worked',
                  '@mail.ru', [settings.EMAIL_RECEPIENT])

    # Если обнаружен дым (smoke_detector),
    # немедленно выключить следующие приборы
    # [air_conditioner, bedroom_light, bathroom_light, boiler, washing_machine],
    # и ни при каких условиях не включать их, пока дым не исчезнет.
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

    # Если стиральная машина сломана, выключить
    if indicators['washing_machine'] == 'broken':
        change.append({'name': 'washing_machine', 'value': 'off'})

    # Если в спальне кто-то есть, включить свет
    if indicators['bedroom_presence'] is True or indicators['bedroom_motion'] is True:
        if indicators['bedroom_light'] is False:
            change.append({'name': 'bedroom_light', 'value': True})

    # Если в ванной кто-то есть, включить свет
    if indicators['bathroom_presence'] is True or indicators['bathroom_motion'] is True:
        if indicators['bathroom_light'] is False:
            change.append({'name': 'bathroom_light', 'value': True})

    # 2 Если холодная вода (cold_water) закрыта, немедленно выключить бойлер (boiler) и
    # стиральную машину (washing_machine)
    # и ни при каких условиях не включать их, пока холодная вода не будет снова открыта.
    if indicators['cold_water'] is False:
        # rdb.set_trace()
        if indicators['boiler'] is True:
            change.append({'name': 'boiler', 'value': False})
        if indicators['washing_machine'] == 'on':
            change.append({'name': 'washing_machine', 'value': 'off'})

    # Если есть изменения, отправляем на сервер
    if len(change) > 0:
        change_settings(change)
