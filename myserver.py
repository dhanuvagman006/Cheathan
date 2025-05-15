from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_cors import CORS
import json
import os
from dotenv import load_dotenv
from functools import lru_cache
from datetime import datetime, timedelta
import requests
import secrets

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Secure random secret key
CORS(app)  # Enable CORS for cross-origin requests

# Configuration
BASE_URL = "http://api.openweathermap.org/data/2.5"
API_KEY = "ff7e2bdaf7c38b91b5b184c9576424ca"

USERS_FILE = 'users.json'

# Load users from JSON file
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

# Save users to JSON file
def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

# Cache weather API requests
@lru_cache(maxsize=100)
def cached_weather_request(url):
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        users = load_users()
        
        if email in users and users[email]['password'] == password:

            session['username'] = users[email]['username']
            session['email'] = users[email]['email']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form['email'].strip()
        phone = request.form['phone'].strip()
        country = request.form['country'].strip()
        
        users = load_users()
        
        if email in users:
            flash('Username already exists!', 'warning')
        else:
            users[email] = {
                'username':username,
                'password': password,
                'email': email,
                'phone': phone,
                'country': country
            }
            save_users(users)
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    
    users = load_users()
    username = session['username']
    location = users.get(username, {}).get('country', 'Unknown Location')
    
    return render_template('dashboard.html', username=username, location=location)

@app.route('/check')
def check():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    
    users = load_users()
    username = session['username']
    email = session['email']
    
    location = users.get(username, {}).get('country', 'Unknown Location')
    
    return render_template('check.html', username=username, location=location)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/get-weather')
def get_weather():
    city = request.args.get('city')
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    if not (city or (lat and lon)):
        return jsonify({'cod': 400, 'message': 'City or coordinates required'}), 400

    try:
        if city:
            url = f"{BASE_URL}/weather?q={city.strip()}&appid={API_KEY}&units=metric"
        else:
            url = f"{BASE_URL}/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
        
        data = cached_weather_request(url)
        
        if data.get('cod') != 200:
            return jsonify({'cod': data.get('cod'), 'message': data.get('message')}), 404

        # Store searched location in users.json
        if 'username' in session:
            users = load_users()
            email = session['email']
            if email in users:
                if 'searched_locations' not in users[email]:
                    users[email]['searched_locations'] = []
                
                location = data['name']
                if location not in users[email]['searched_locations']:
                    users[email]['searched_locations'].append(location)
                    save_users(users)

        return jsonify({
            'cod': 200,
            'name': data['name'],
            'description': data['weather'][0]['description'],
            'icon': data['weather'][0]['icon'],
            'temp': round(data['main']['temp'], 1),
            'humidity': data['main']['humidity'],
            'wind_speed': round(data['wind']['speed'], 1),
            'lat': data['coord']['lat'],
            'lon': data['coord']['lon']
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'cod': 500, 'message': f'Failed to fetch weather data: {str(e)}'}), 500

@app.route('/get-forecast')
def get_forecast():
    city = request.args.get('city')
    
    if not city:
        return jsonify({'cod': 400, 'message': 'City parameter is required'}), 400

    try:
        url = f"{BASE_URL}/forecast?q={city.strip()}&appid={API_KEY}&units=metric"
        data = cached_weather_request(url)

        if data.get('cod') != '200':
            return jsonify({'cod': data.get('cod'), 'message': data.get('message')}), 404

        forecast_list = [
            {
                'dt_txt': item['dt_txt'],
                'temp': round(item['main']['temp'], 1),
                'description': item['weather'][0]['description'],
                'icon': item['weather'][0]['icon']
            }
            for item in data['list']
        ]

        return jsonify({
            'cod': 200,
            'city': data['city']['name'],
            'forecast': forecast_list
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'cod': 500, 'message': f'Failed to fetch forecast data: {str(e)}'}), 500

@app.route('/get-weekly-forecast')
def get_weekly_forecast():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    if not (lat and lon):
        return jsonify({'cod': 400, 'message': 'Coordinates required'}), 400

    try:
        today = datetime.now().strftime('%Y-%m-%d')
        next_week = (datetime.now() + timedelta(days=6)).strftime('%Y-%m-%d')
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&start_date={today}&end_date={next_week}"
        data = cached_weather_request(url)

        if not data.get('daily'):
            return jsonify({'cod': 404, 'message': 'No forecast data available'}), 404

        weather_icons = {
            0: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/clear-day.svg",
            1: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/mostly-clear-day.svg",
            2: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/partly-cloudy-day.svg",
            3: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/cloudy.svg",
            45: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/fog.svg",
            48: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/fog.svg",
            51: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/drizzle.svg",
            61: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/rain.svg",
            71: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/snow.svg",
            80: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/showers-day.svg",
            95: "https://cdn.jsdelivr.net/gh/basmilius/weather-icons/production/fill/all/thunderstorms.svg",
        }

        forecast = [
            {
                'day': datetime.strptime(date, '%Y-%m-%d').strftime('%a'),
                'max_temp': round(data['daily']['temperature_2m_max'][i], 1),
                'min_temp': round(data['daily']['temperature_2m_min'][i], 1),
                'icon': weather_icons.get(data['daily']['weathercode'][i], weather_icons[3])
            }
            for i, date in enumerate(data['daily']['time'])
        ]

        return jsonify({
            'cod': 200,
            'forecast': forecast
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'cod': 500, 'message': f'Failed to fetch weekly forecast: {str(e)}'}), 500

@app.route('/get-city-suggestions')
def get_city_suggestions():
    query = request.args.get('query')
    
    if not query or len(query) < 3:
        return jsonify({'cod': 400, 'message': 'Query must be at least 3 characters'}), 400

    try:
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={query.strip()}&limit=5&appid={API_KEY}"
        data = cached_weather_request(url)

        cities = [
            {
                'name': item['name'],
                'country': item['country'],
                'lat': item['lat'],
                'lon': item['lon']
            }
            for item in data
        ]
        return jsonify({
            'cod': 200,
            'cities': cities
        })

    except requests.exceptions.RequestException as e:
        return jsonify({'cod': 500, 'message': f'Failed to fetch city suggestions: {str(e)}'}), 500

@app.route('/admin')
def admin():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    
    # For now, we'll allow any logged-in user to access admin
    # In a real application, you should add proper admin authentication
    users = load_users()
    user_details = []
    
    for email, data in users.items():
        user_details.append({
            'username': data.get('username', 'N/A'),
            'email': email,
            'phone': data.get('phone', 'N/A'),
            'country': data.get('country', 'N/A'),
            'searched_locations': data.get('searched_locations', []),
            'messages': data.get('messages', [])  # Add messages to user details
        })
    
    return render_template('admin.html', users=user_details)

@app.route('/contact', methods=['POST'])
def contact():
    if 'username' not in session:
        flash('Please login first.', 'danger')
        return redirect(url_for('login'))
    
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')
    
    if not all([name, email, message]):
        flash('All fields are required', 'danger')
        return redirect(url_for('dashboard'))
    
    users = load_users()
    user_email = session['email']
    
    if user_email in users:
        if 'messages' not in users[user_email]:
            users[user_email]['messages'] = []
        
        users[user_email]['messages'].append({
            'name': name,
            'email': email,
            'message': message,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
        save_users(users)
        flash('Message sent successfully!', 'success')
    else:
        flash('Error sending message', 'danger')
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)