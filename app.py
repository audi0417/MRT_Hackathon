import json
from bs4 import BeautifulSoup
from flask import Flask, render_template, request
from func import  timed_cache
import requests
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
app = Flask(__name__)

CLIENT_ID = 't112ab8033-b77dbe3d-6d9c-41c8'
CLIENT_SECRET = 'da595af2-d0bd-4e68-ac6f-4098fb030168'

@app.route("/")
def hello_world():

    return render_template("index.html", title="Hello")


# 獲取Google Maps經緯度

def get_map_location(location_search):
    url = f"https://www.google.com/maps/search/{location_search}"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    script_tag = soup.find('script', text=lambda x: x and 'window.APP_INITIALIZATION_STATE' in x.string)
    if script_tag:
        # 提取經緯度信息
        content = script_tag.string
        initial_pos = content.index(';window.APP_INITIALIZATION_STATE')
        data = content[initial_pos + 36:initial_pos + 85]
        data = data.replace(']', '')
        parts = data.split(',')
        latitude = parts[2]
        longitude = parts[1]
        return f"{latitude},{longitude}"
    return None

# 獲取TDX API授權令牌
def get_authorization_token():
    token_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(token_url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = json.loads(response.text)
    return data['access_token']

def parse_travel_info(json_data, start, end):
    # 判断json_data是否为空
    if not json_data:
        return [['無法規劃行程', start, end, '0']]
    print(json_data)
    min_travel_time = float('inf')
    min_route_index = -1

    for i, route in enumerate(json_data):
        if route['travel_time'] < min_travel_time:
            min_travel_time = route['travel_time']
            min_route_index = i

    if min_route_index == -1:
        return [['無法規劃行程', start, end, '0']]

    result = []
    route = json_data[min_route_index]
    sections = route['sections']
    last_valid_place = start  

    for i, section in enumerate(sections):
        transport_mode = get_transport_mode(section)

        start_point = section.get('departure', {}).get('place', {}).get('name', last_valid_place)
        end_point = section.get('arrival', {}).get('place', {}).get('name', None)
        
        if not end_point:
            for next_section in sections[i+1:]:
                next_start_point = next_section.get('departure', {}).get('place', {}).get('name', None)
                if next_start_point:
                    end_point = next_start_point
                    break
 
            if not end_point:
                end_point = end

        duration = section.get('travelSummary', {}).get('duration', "0")

        last_valid_place = end_point 

        route_result = [transport_mode, start_point, end_point, str(duration)]
        

        if section.get('type') == 'cycle':
            you_bike_info_start = get_youbike_info(section.get('departure', {}).get('place', {}).get('name', ''))
            you_bike_info_end = get_youbike_info(section.get('arrival', {}).get('place', {}).get('name', ''))
            if you_bike_info_start:
                you_bike_text_start = f"起點可用車輛：{you_bike_info_start.get('availableBikes', 0)}輛,目前空位：{you_bike_info_start.get('emptySpace', 0)},狀態：{'可用' if you_bike_info_start.get('operating', False) else '不可用'}"
                route_result.append(you_bike_text_start)

            if you_bike_info_end:
                you_bike_text_end = f"終點可用車輛：{you_bike_info_end.get('availableBikes', 0)}輛,目前空位：{you_bike_info_end.get('emptySpace', 0)},狀態：{'可用' if you_bike_info_end.get('operating', False) else '不可用'}"
                route_result.append(you_bike_text_end)
        result.append(route_result)
    print(result)
    return result

def get_transport_mode(section):
    mode = ""
    section_type = section['type']
    if section_type == "pedestrian":
        mode = "步行"
    elif section_type == "cycle":
        mode = "共享單車"
    elif section_type == "transit":
        transport = section['transport']
        if transport and transport['mode'] == "MRT":
            mode = f"捷運({transport['name']})"
        else:
            mode = f"公車({transport['name']})"
    elif section_type == "pedestrian-station":
        mode = "站內步行"
    elif section_type == "waiting":
        mode = "等待/轉乘"
    return mode




def fetch_data(url):
    return requests.get(url).json()

def get_all_youbike_data():
    urls = [
        "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json",
        "https://data.ntpc.gov.tw/api/datasets/71cd1490-a2df-4198-bef1-318479775e8a/json?size=9999",
        "https://data.ntpc.gov.tw/api/datasets/010e5b15-3823-4b20-b401-b1cf000550c5/json?size=9999"
    ]

    all_youbike_data = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_url = {executor.submit(fetch_data, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            data = future.result()
            all_youbike_data.extend(data)
    return all_youbike_data

@timed_cache(seconds=300, maxsize=9999)
@lru_cache(maxsize=9999)
def get_youbike_info(station_name):
    all_youbike_data = get_all_youbike_data()

    # 搜尋站名相符的資料
    station_info = next((station for station in all_youbike_data if station['sna'] == station_name), None)

    if station_info:
        try: 
            data = {
                'availableBikes': station_info['sbi'],
                'emptySpace': station_info['bemp'],
                'operating': station_info['act'] == '1'
            }
            return data
        except:
            data = {
                    'availableBikes': station_info['available_rent_bikes'],
                    'emptySpace': station_info['available_return_bikes'],
                    'operating': station_info['act'] == '1'
                }
            return data
        
    else:
        return None

# 獲取TDX API行程規劃
@app.route('/', methods=['GET', 'POST'])
def get_travel_info():
    if request.method == 'POST': 
        start = request.form.get('start')
        end = request.form.get('end')
        start_location = get_map_location(start)
        end_location = get_map_location(end)
        
        url = f' https://tdx.transportdata.tw/api/maas/routing?origin={start_location}&destination={end_location}&gc=1&top=1&transit=5%2C6&transfer_time=15%2C60&first_mile_mode=0%2C3&first_mile_time=15&last_mile_mode=0%2C3&last_mile_time=15'
       
        headers = {"Authorization": f"Bearer {get_authorization_token()}"}
        response = requests.get(url, headers=headers)
        data = json.loads(response.text)
        route_data = parse_travel_info(data['data']['routes'], start, end)
        print(route_data)
        return json.dumps(route_data)


if __name__ == '__main__':
    app.run(debug=True)