import matplotlib
matplotlib.use('Agg')


from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import random
import matplotlib.pyplot as plt
import io
import base64
import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///carbon_footprint.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Expanded emission factors
EMISSION_FACTORS = {
    'car': 0.2,
    'bus': 0.1,
    'train': 0.05,
    'plane': 0.25,
    'electricity': 0.5,
    'natural_gas': 0.2,
    'waste': 0.1,
    'water': 0.001,
    'meat': 0.015,
    'vegetables': 0.002,
}

AVERAGE_FOOTPRINT = 20

ECO_TIPS = {
    'car': "Consider carpooling or using an electric vehicle to reduce emissions.",
    'bus': "Great job using public transport! Try to use it more often.",
    'train': "Trains are an eco-friendly option. Keep it up!",
    'plane': "Try to reduce air travel or offset your flights when possible.",
    'electricity': "Switch to energy-efficient appliances and use renewable energy sources.",
    'natural_gas': "Improve your home's insulation to reduce heating needs.",
    'waste': "Increase recycling and composting to reduce waste emissions.",
    'water': "Fix leaks and use water-saving fixtures to reduce water consumption.",
    'meat': "Consider reducing meat consumption, especially beef, to lower your footprint.",
    'vegetables': "Keep up the plant-based diet! It's great for the environment.",
}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    activities = db.relationship('Activity', backref='user', lazy=True)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_data = db.Column(db.JSON, nullable=False)
    total_footprint = db.Column(db.Float, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('calculate_footprint'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash('Registration successful. Please log in.')
        return redirect(url_for('calculate_footprint'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('calculate_footprint'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('calculate_footprint'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/calculate', methods=['GET', 'POST'])
@login_required
def calculate_footprint():
    if request.method == 'POST':
        activity_data = {activity: float(request.form[activity]) for activity in EMISSION_FACTORS.keys()}
        
        df = pd.DataFrame(list(activity_data.items()), columns=['activity', 'value'])
        df['emission_factor'] = df['activity'].map(EMISSION_FACTORS)
        df['footprint'] = df['value'] * df['emission_factor']
        
        total_footprint = df['footprint'].sum()
        footprint_breakdown = df.set_index('activity')['footprint'].to_dict()
        
        comparison = (total_footprint / AVERAGE_FOOTPRINT) * 100
        
        # Generate eco-tip
        eco_tip = generate_eco_tip(activity_data)

        # Save to database
        new_activity = Activity(
            date=datetime.datetime.now(),
            user_id=current_user.id,
            activity_data=activity_data,
            total_footprint=total_footprint
        )
        db.session.add(new_activity)
        db.session.commit()

        return render_template('result.html', footprint=total_footprint, breakdown=footprint_breakdown, eco_tip=eco_tip, comparison=comparison)
    
    return render_template('calculate.html', activities=EMISSION_FACTORS.keys())

@app.route('/history')
@login_required
def history():
    activities = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.date.desc()).all()
    return render_template('history.html', activities=activities)

@app.route('/graph')
@login_required
def graph():
    activities = Activity.query.filter_by(user_id=current_user.id).order_by(Activity.date).all()
    dates = [activity.date for activity in activities]
    footprints = [activity.total_footprint for activity in activities]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, footprints, marker='o')
    plt.title('Your Carbon Footprint Over Time')
    plt.xlabel('Date')
    plt.ylabel('Carbon Footprint (kg CO2)')
    plt.xticks(rotation=45)
    plt.tight_layout()

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()

    return render_template('graph.html', graph_url=graph_url)

def generate_eco_tip(activity_data):
    tips = {
        'car': "Consider carpooling or using public transport to reduce your carbon footprint.",
        'electricity': "Switch to energy-efficient appliances and LED bulbs to save electricity.",
        'natural_gas': "Improve your home's insulation to reduce heating costs and energy usage.",
        # Add more tips for other activities
    }
    
    # Choose a random tip based on the activities
    relevant_tips = [tips[activity] for activity in activity_data if activity in tips]
    return random.choice(relevant_tips) if relevant_tips else "Try to reduce your overall energy consumption."

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
