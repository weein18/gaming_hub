from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from werkzeug.utils import secure_filename
# from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
import base64
from sqlalchemy import or_
import re
import dns.resolver
from datetime import datetime, timedelta
import pytz
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from sqlalchemy import or_, func
import resend
import threading
from bot import start_bot_thread, send_telegram_message






if not os.path.exists('instance'):
    os.makedirs('instance')

app = Flask(__name__)

ADMIN_ACCESS_KEY = os.getenv('ADMIN_ACCESS_KEY')
uri = os.getenv('DATABASE_URL', 'sqlite:///database.db')
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 1,
    'max_overflow': 0,
    'pool_pre_ping': True,
}
app.config['SECRET_KEY'] = os.getenv('SECRET_ACCESS_KEY', 'default_local_secret')

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# app.config['MAIL_SERVER'] = 'smtp-relay.brevo.com'
# app.config['MAIL_PORT'] = 465
# app.config['MAIL_USE_TLS'] = False
# app.config['MAIL_USE_SSL'] = True 

# app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
# app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
# app.config['MAIL_DEFAULT_SENDER'] = 'elitehub040@gmail.com'

# mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash("Only admins can access this page!", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(1000), nullable=False)
    xp = db.Column(db.Integer, default=0)
    rank = db.Column(db.String(100), default='Silver')
    bio = db.Column(db.String(200), default='No bio yet...')
    steam_url = db.Column(db.String(200), default='')
    email = db.Column(db.String(200), unique=True, nullable=False)
    favorite_team = db.Column(db.String(50), default=' ')
    avatar = db.Column(db.Text, default='default.png')
    is_admin = db.Column(db.Boolean, default=False)
    telegram_id = db.Column(db.String(50), default=None)
    telegram_chat_id = db.Column(db.String(50), default=None)
    telegram_link_code = db.Column(db.String(50), default=None)
class Match(db.Model):
    pandascore_id = db.Column(db.Integer, default=None)
    id = db.Column(db.Integer, primary_key=True)
    tournament_name = db.Column(db.String(100), nullable=False, default='BLAST Rivals 2026 Season 1')
    team1 = db.Column(db.String(50), nullable=False)
    team2 = db.Column(db.String(50), nullable=False)
    team1_logo = db.Column(db.String(500), default='')
    team2_logo = db.Column(db.String(500), default='')
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='Upcoming')
    final_score = db.Column(db.String(10), default='')
    match_type = db.Column(db.String(10), default="BO3")
    predictions = db.relationship('Prediction', backref='match', lazy=True)
    def is_started(self):
        try:
            germany_tz = pytz.timezone('Europe/Berlin')
            now = datetime.now(germany_tz).replace(tzinfo=None)
            clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', self.date.strip())
            t_str = self.time.strip()
            if ':' in t_str:
                h, m = t_str.split(':')
                t_str = f"{int(h):02d}:{int(m):02d}"
            match_dt = datetime.strptime(f"{clean_date} 2026 {t_str}", "%B %d %Y %H:%M")
            print(f"--- MATCH {self.id} --- Germany Now: {now} | Match Time: {match_dt}")
            return now >= match_dt
        except Exception as e:
            print(f"!!! TIME ERROR: {e}")
            return False
class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    prize_pool = db.Column(db.String(50))
    date = db.Column(db.String(50))
    xp_reward = db.Column(db.String(50))
    image_url = db.Column(db.String(500), default='')
class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'), nullable=False)
    prediction_score = db.Column(db.String(10), nullable=False)
    is_correct = db.Column(db.Boolean, default=None)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# !!! REGISTER !!!

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        username = re.sub('<[^<]+?>', '', username)
        email = request.form.get('email', '').strip().lower()
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            flash("Please enter a valid email address (e.g. name@gmail.com)!")
            return redirect(url_for('register'))
        domain = email.split('@')[-1]
        try:
            dns.resolver.resolve(domain, 'MX')
        except Exception:
            flash("This email domain does not exist! Use a real provider like Gmail.")
            return redirect(url_for('register'))
        fav_team = request.form.get('favorite_team', '').strip()
        fav_team = re.sub('<[^<]+?>', '', fav_team)
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password') 
        if not username:
            flash("Username is required!")
            return redirect(url_for('register'))
        if password != confirm_password:
            flash("Passwords do not match!")
            return redirect(url_for('register'))
        user_exists = User.query.filter((User.username == username) | (User.email == email)).first()
        if user_exists:
            flash("Username or Email already exists!")
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username, 
            email=email, 
            password=hashed_password, 
            favorite_team=fav_team
        )       
        db.session.add(new_user)
        db.session.commit()       
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/')
def index():
    stats = {
        'total_users': User.query.count(),
        'active_matches': Match.query.filter_by(status='Upcoming').count(),
        'total_predictions': Prediction.query.count()
    }
    featured_matches = Match.query.filter_by(status='Upcoming').limit(3).all()    
    return render_template('index.html', stats=stats, featured_matches=featured_matches)

# !!! LOGIN !!!

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')       
        user = User.query.filter_by(username=username).first()      
        if user:
            is_valid = check_password_hash(user.password, password)
            if is_valid:
                login_user(user)
                return redirect(url_for('index'))
            else:
                flash('WRONG PASSWORD!')
                print(f"User {username} exists, but password {password} is wrong for hash {user.password}")
        else:
            flash('USER NOT FOUND!')
            print(f"User {username} not found in database.")
    return render_template('auth/login.html')

# !!! MATCHES !!!

@app.route('/matches')
def matches():
    upcoming_names_raw = db.session.query(Match.tournament_name).filter(
        Match.status == 'Upcoming'
    ).distinct().all()
    active_names = [n[0].strip() for n in upcoming_names_raw if n and n[0]]
    tournaments_for_page = []
    for name in active_names:
        t = Tournament.query.filter(func.lower(Tournament.name) == name.lower()).first()
        if not t:
            t = Tournament.query.filter(
                or_(
                    Tournament.name.ilike(f"%{name}%"),
                    func.lower(name).contains(func.lower(Tournament.name))
                )
            ).first()
        if not t:
            t = Tournament(
                name=name,
                prize_pool="TBD",
                date="Ongoing",
                xp_reward="100 XP",
                image_url=""
            )
        tournaments_for_page.append(t)
    return render_template('games/matches.html', tournaments=tournaments_for_page)

@app.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    total_preds = Prediction.query.filter_by(user_id=user.id).count()
    correct_preds = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
    if total_preds > 0:
        accuracy = int((correct_preds / total_preds) * 100)
    else:
        accuracy = 0
    xp = user.xp
    if xp >= 9500:   user.rank = 'The Global Elite'
    elif xp >= 8900: user.rank = 'Supreme Master First Class'
    elif xp >= 8300: user.rank = 'Legendary Eagle Master'
    elif xp >= 7700: user.rank = 'Legendary Eagle'
    elif xp >= 7100: user.rank = 'Distinguished Master Guardian'
    elif xp >= 6500: user.rank = 'Master Guardian Elite'
    elif xp >= 5900: user.rank = 'Master Guardian II'
    elif xp >= 5300: user.rank = 'Master Guardian I'
    elif xp >= 4700: user.rank = 'Gold Nova Master'
    elif xp >= 4100: user.rank = 'Gold Nova III'
    elif xp >= 3500: user.rank = 'Gold Nova II'
    elif xp >= 2900: user.rank = 'Gold Nova I'
    elif xp >= 2300: user.rank = 'Silver Elite Master'
    elif xp >= 1700: user.rank = 'Silver Elite'
    elif xp >= 1100: user.rank = 'Silver IV'
    elif xp >= 600:  user.rank = 'Silver III'
    elif xp >= 300:  user.rank = 'Silver II'
    else:            user.rank = 'Silver I'
    db.session.commit()
    prediction_dates = [
    p.created_at.strftime('%Y-%m-%d')
    for p in Prediction.query.filter_by(user_id=user.id).all()
    if p.created_at is not None
    ]
    return render_template('user/profile.html', 
                           user=user, 
                           accuracy=accuracy, 
                           total_wins=correct_preds,
                           prediction_dates=prediction_dates)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        old_pass = request.form.get('old_password')
        new_pass = request.form.get('new_password')
        confirm_pass = request.form.get('confirm_password')
        if old_pass and new_pass:
            if not check_password_hash(current_user.password, old_pass):
                flash("Old password incorrect!")
                return redirect(url_for('settings'))
            if new_pass != confirm_pass:
                flash("New passwords do not match!")
                return redirect(url_for('settings'))
            if len(new_pass) < 6:
                flash("New password is too short!")
                return redirect(url_for('settings'))
            current_user.password = generate_password_hash(new_pass)
            flash("Password security updated!")
        new_username = request.form.get('username')
        new_username = re.sub('<[^<]+?>', '', new_username).strip()
        if new_username != current_user.username:
            user_exists = User.query.filter_by(username=new_username).first()
            if user_exists:
                flash("This username is already taken!")
                return redirect(url_for('settings'))
            current_user.username = new_username
        raw_steam_url = request.form.get('steam_url', '').strip()
        if raw_steam_url:
            if raw_steam_url.startswith('https://steamcommunity.com/'):
                current_user.steam_url = raw_steam_url
            else:
                current_user.steam_url = ""
                flash("Invalid Steam URL! Only official Steam links allowed.")
        else:
            current_user.steam_url = ""
        raw_bio = request.form.get('bio', '')
        current_user.bio = re.sub('<[^<]+?>', '', raw_bio).strip()
        raw_team = request.form.get('favorite_team', '')
        current_user.favorite_team = re.sub('<[^<]+?>', '', raw_team).strip()
        current_user.email = request.form.get('email')
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                img_data = file.read()
                base64_encoded = base64.b64encode(img_data).decode('utf-8')
                current_user.avatar = f"data:{file.content_type};base64,{base64_encoded}"
        db.session.commit()
        flash('Profile settings saved!')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('user/settings.html', user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    user = current_user
    total_preds = Prediction.query.filter_by(user_id=user.id).count()
    correct_preds = Prediction.query.filter_by(user_id=user.id, is_correct=True).count()
    accuracy = int((correct_preds / total_preds) * 100) if total_preds > 0 else 0
    all_user_preds = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.id.desc()).all()
    win_streak = 0
    for pred in all_user_preds:
        if pred.is_correct is True:
            win_streak += 1
        elif pred.is_correct is False:
            break
        else:
            continue
    xp = user.xp
    if xp >= 9500:   
        user.rank, next_rank, current_threshold, next_threshold = 'The Global Elite', 'MAX', 9500, 10000
    elif xp >= 8900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Supreme Master First Class', 'The Global Elite', 8900, 9500
    elif xp >= 8300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Legendary Eagle Master', 'Supreme Master First Class', 8300, 8900
    elif xp >= 7700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Legendary Eagle', 'Legendary Eagle Master', 7700, 8300
    elif xp >= 7100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Distinguished Master Guardian', 'Legendary Eagle', 7100, 7700
    elif xp >= 6500: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian Elite', 'Distinguished Master Guardian', 6500, 7100
    elif xp >= 5900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian II', 'Master Guardian Elite', 5900, 6500
    elif xp >= 5300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Master Guardian I', 'Master Guardian II', 5300, 5900
    elif xp >= 4700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova Master', 'Master Guardian I', 4700, 5300
    elif xp >= 4100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova III', 'Gold Nova Master', 4100, 4700
    elif xp >= 3500: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova II', 'Gold Nova III', 3500, 4100
    elif xp >= 2900: 
        user.rank, next_rank, current_threshold, next_threshold = 'Gold Nova I', 'Gold Nova II', 2900, 3500
    elif xp >= 2300: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver Elite Master', 'Gold Nova I', 2300, 2900
    elif xp >= 1700: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver Elite', 'Silver Elite Master', 1700, 2300
    elif xp >= 1100: 
        user.rank, next_rank, current_threshold, next_threshold = 'Silver IV', 'Silver Elite', 1100, 1700
    elif xp >= 600:  
        user.rank, next_rank, current_threshold, next_threshold = 'Silver III', 'Silver IV', 600, 1100
    elif xp >= 300:  
        user.rank, next_rank, current_threshold, next_threshold = 'Silver II', 'Silver III', 300, 600
    else:            
        user.rank, next_rank, current_threshold, next_threshold = 'Silver I', 'Silver II', 0, 300
    db.session.commit()
    if user.rank == 'The Global Elite':
        progress_percent = 100
    else:
        xp_in_current_level = xp - current_threshold
        level_duration = next_threshold - current_threshold
        progress_percent = int((xp_in_current_level / level_duration) * 100)
        progress_percent = max(0, min(100, progress_percent))
    featured_match = Match.query.filter_by(status="Upcoming").first()
    recent_predictions = Prediction.query.filter_by(user_id=user.id).order_by(Prediction.id.desc()).limit(10).all()
    return render_template('admin/dashboard.html', 
                           user=user, 
                           accuracy=accuracy, 
                           total_wins=correct_preds,
                           total_preds=total_preds,
                           next_rank=next_rank,
                           next_threshold=next_threshold,
                           progress_percent=progress_percent,
                           win_streak=win_streak,
                           featured_match=featured_match,
                           predictions_count=len(recent_predictions),
                           recent_predictions=recent_predictions)

@app.route('/tournament/<name>')
@login_required
def tournament(name):
    url_name = name.replace('-', ' ') 
    tournament_info = Tournament.query.filter(Tournament.name.ilike(url_name)).first()
    if tournament_info:
        real_db_name = tournament_info.name
    else:
        real_db_name = url_name
    selected_date = request.args.get('date')
    all_dates_query = db.session.query(Match.date).filter(
        Match.tournament_name.ilike(real_db_name)
    ).distinct().all()
    all_dates = [d[0] for d in all_dates_query if d[0]]
    def parse_date_string(date_str):
        try:
            clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
            return datetime.strptime(clean_date, "%B %d")
        except:
            try:
                return datetime.strptime(clean_date, "%B %d %Y")
            except:
                return datetime.min
    all_dates.sort(key=parse_date_string)
    if not selected_date and all_dates:
        selected_date = all_dates[0]
    tournament_matches = Match.query.filter(
        Match.tournament_name.ilike(real_db_name),
        Match.date == selected_date
    ).all()
    tournament_matches.sort(key=lambda x: datetime.strptime(x.time.strip(), '%H:%M') if ':' in x.time else x.time)
    user_predictions = Prediction.query.filter_by(user_id=current_user.id).all()
    preds_dict = {p.match_id: p.prediction_score for p in user_predictions}
    return render_template('tournament.html',
                           tournament_name=real_db_name,
                           tournament=tournament_info,
                           matches=tournament_matches,
                           all_dates=all_dates,
                           current_date=selected_date,
                           user_preds=preds_dict)

@app.route('/all-tournament')
@login_required
def all_tournaments():
    tournaments = db.session.query(Match.tournament_name).distinct().all()
    tour_list = [{"display": t[0], "url": t[0].lower().replace(' ', '-')} for t in tournaments]
    return render_template('all_tournaments.html', tournaments=tour_list)

@app.route('/admin/add_match', methods=['GET', 'POST'])
@login_required
def add_match():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        t_name = request.form.get('tournament')
        t1 = request.form.get('team1')
        t2 = request.form.get('team2')
        m_date = request.form.get('date')
        m_time = request.form.get('time')
        m_type = request.form.get('match_type')
        new_match = Match(
            tournament_name=t_name,
            team1=t1,
            team2=t2,
            date=m_date,
            time=m_time,
            match_type=m_type
        )
        db.session.add(new_match)
        db.session.commit()
        flash('Match added successfully!', 'success')
        return redirect(url_for('add_match'))
    all_tournaments = Tournament.query.all()
    return render_template('admin/add_match.html', tournaments=all_tournaments)

@app.route("/admin/add_tournament", methods=["GET", "POST"])
@login_required
def add_tournament():
        if not current_user.is_admin:
            flash("Only admin page!!!")
            return redirect(url_for("index"))
        if request.method == 'POST':
            new_t = Tournament(
                name=request.form.get('name'),
                prize_pool=request.form.get('prize_pool'),
                date=request.form.get('date'),
                xp_reward=request.form.get('xp_reward') 
            )
            db.session.add(new_t)
            db.session.commit()
            return redirect(url_for('matches'))
        return render_template('admin/add_tournament.html')

@app.route('/predict/<int:match_id>', methods=['POST'])
@login_required
def predict(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status != 'Upcoming' or match.is_started():
        flash("Too late! The match has already started or finished.")
        return redirect(request.referrer)
    score = request.form.get('predicted_score') 
    existing = Prediction.query.filter_by(user_id=current_user.id, match_id=match_id).first()
    if existing:
        existing.prediction_score = score
    else:
        new_pred = Prediction(user_id=current_user.id, match_id=match_id, prediction_score=score)
        db.session.add(new_pred)
    db.session.commit()
    flash("Prediction saved!")
    return redirect(request.referrer)

@app.route('/admin/manage-matches')
def manage_matches():
    if not current_user.is_admin:
        flash("Only admins can access this page!")
        return redirect(url_for("index"))
    active_matches = Match.query.filter_by(status='Upcoming').all()
    return render_template('admin/manage_matches.html', active_matches=active_matches)

@app.route('/admin/close-match/<int:match_id>', methods=['POST'])
@login_required
def close_match(match_id):
    if not current_user.is_admin:
        flash("Only admin access!!!")
        return redirect(url_for("index"))
    final_score = request.form.get('final_score')
    match = db.session.get(Match, match_id)   
    if match and final_score:
        match.final_score = final_score
        match.status = 'Finished'
        predictions = Prediction.query.filter_by(match_id=match_id).all()
        telegram_notifications = []
        for pred in predictions:
            user = db.session.get(User, pred.user_id)
            is_correct = pred.prediction_score == final_score
            pred.is_correct = is_correct
            if user and is_correct:
                user.xp += 100
            if user and user.telegram_chat_id:
                result_icon = "✅" if is_correct else "❌"
                result_text = "Correct prediction! <b>+100 XP</b>" if is_correct else "Not this time — keep going."
                telegram_notifications.append((
                    user.telegram_chat_id,
                    f"{result_icon} <b>Match result</b>\n\n"
                    f"⚔️ <b>{match.team1}</b> {final_score} <b>{match.team2}</b>\n"
                    f"Your prediction: <b>{pred.prediction_score}</b>\n\n"
                    f"{result_text}"
                ))
        db.session.commit()
        for chat_id, text in telegram_notifications:
            send_telegram_message(chat_id, text)      
        flash(f"Match {match.team1} vs {match.team2} closed with score {final_score}!") 
    return redirect(url_for('manage_matches'))

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

# @app.route('/request-password-reset', methods=['POST'])
# @login_required
# def request_password_reset():
#     email = current_user.email
#     user = User.query.filter_by(email=email).first()
#     if user:
#         token = s.dumps(email, salt='password-reset-salt')
#         link = url_for('reset_password', token=token, _external=True)
        
#         try:
#             msg = Message(
#                 subject='Password Reset Request — Command Center', 
#                 sender=app.config['MAIL_DEFAULT_SENDER'], 
#                 recipients=[email]
#             )
#             msg.body = f'''Hello {user.username},

# You requested a password reset from your Command Center dashboard. 
# To pick a new password, click on the link below:

# {link}

# This link will expire in 30 minutes. If you did not make this request, simply ignore this email.
# '''
#             mail.send(msg)
#             flash("Check your email inbox! We have dispatched a secure reset link.", "success")
#         except Exception as e:
#             print(f"!!! MAIL SENDING ERROR: {e}")
#             flash("Failed to send mail. Please verify mail server configuration.", "danger")
#     else:
#         flash("Account security context error. User not found.", "danger")
#     return redirect(url_for('dashboard'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if user:
            token = s.dumps(email, salt='password-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            def send_email(user_email, reset_link):
                try:
                    import httpx
                    response = httpx.post(
                        "https://api.brevo.com/v3/smtp/email",
                        headers={
                            "api-key": os.getenv("BREVO_API_KEY"),
                            "Content-Type": "application/json"
                        },
                        json={
                            "sender": {"name": "EliteHub", "email": "elitehub040@gmail.com"},
                            "to": [{"email": user_email}],
                            "subject": "EliteHub — Password Reset",
                            "htmlContent": f'''
                                <div style="background:#000;padding:40px;font-family:sans-serif;color:white;">
                                    <h2 style="color:#e30613;">EliteHub</h2>
                                    <p>Click below to reset your password:</p>
                                    <a href="{reset_link}" style="display:inline-block;margin:20px 0;padding:12px 28px;background:#e30613;color:white;text-decoration:none;border-radius:8px;font-weight:bold;">
                                        Reset Password
                                    </a>
                                    <p style="color:#666;font-size:0.8rem;">Expires in 30 minutes.</p>
                                </div>
                            '''
                        }
                    )
                    print(f"[MAIL] Brevo: {response.status_code} {response.text}")
                except Exception as e:
                    print(f"[MAIL] Failed: {e}")
            threading.Thread(target=send_email, args=(email, reset_url), daemon=True).start()
        flash('If that email exists, a reset link has been sent.', 'info')
        return redirect(url_for('forgot_password'))
    return render_template('auth/forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = s.loads(token, salt='password-reset', max_age=1800)
    except Exception:
        flash('This reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_pass) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(request.url)
        if new_pass != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(request.url)
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('forgot_password'))
        user.password = generate_password_hash(new_pass, method='pbkdf2:sha256')
        db.session.commit()
        flash('Password updated! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/reset_password.html', token=token)

@app.route('/leaderboard')
@login_required
def leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(50).all()
    return render_template('user/leaderboard.html', users=top_users)

def active_roster(players):
    active_players = [
        player for player in players
        if player.get("role") == "player"
        and player.get("active") is not False
    ]
    return active_players[:5]

@app.route('/match/<int:match_id>')
@login_required
def match_analytics(match_id):
    match = db.session.get(Match, match_id)
    if not match:
        flash("Match not found", "danger")
        return redirect(url_for('matches'))
    token = os.getenv("PANDASCORE_TOKEN", "")
    api_match = None
    t1_players = []
    t2_players = []
    t1_recent = []
    t2_recent = []
    maps_data = []
    # if token and match.pandascore_id:
    #     try:
    #         # Full match details
    #         r = requests.get(
    #             f"https://api.pandascore.co/matches/{match.pandascore_id}?token={token}",
    #             timeout=10
    #         )
    #         if r.status_code == 200:
    #             api_match = r.json()
    #             opponents = api_match.get("opponents") or []
    #             # Players from each team
    #             if len(opponents) >= 2:
    #                 t1_id = opponents[0]["opponent"]["id"]
    #                 t2_id = opponents[1]["opponent"]["id"]
    #                 # Team 1 players
    #                 r1 = requests.get(
    #                     f"https://api.pandascore.co/csgo/teams/{t1_id}?token={token}",
    #                     timeout=10
    #                 )
    #                 if r1.status_code == 200:
    #                     t1_players = r1.json().get("players") or []
    #                 # Team 2 players
    #                 r2 = requests.get(
    #                     f"https://api.pandascore.co/csgo/teams/{t2_id}?token={token}",
    #                     timeout=10
    #                 )
    #                 if r2.status_code == 200:
    #                     t2_players = r2.json().get("players") or []
    #                 # Team 1 recent matches
    #                 r3 = requests.get(
    #                     f"https://api.pandascore.co/csgo/teams/{t1_id}/matches?token={token}&filter[status]=finished&per_page=5&sort=-begin_at",
    #                     timeout=10
    #                 )
    #                 if r3.status_code == 200:
    #                     t1_recent = r3.json()
    #                 # Team 2 recent matches
    #                 r4 = requests.get(
    #                     f"https://api.pandascore.co/csgo/teams/{t2_id}/matches?token={token}&filter[status]=finished&per_page=5&sort=-begin_at",
    #                     timeout=10
    #                 )
    #                 if r4.status_code == 200:
    #                     t2_recent = r4.json()
    #             # Maps data (for finished matches)
    #             games = api_match.get("games") or []
    #             for game in games:
    #                 if game.get("finished"):
    #                     maps_data.append({
    #                         "map": (game.get("map") or {}).get("name", "Unknown"),
    #                         "winner": (game.get("winner") or {}).get("name", ""),
    #                         "t1_score": next((t["score"] for t in (game.get("results") or []) if t.get("team_id") == t1_id), 0),
    #                         "t2_score": next((t["score"] for t in (game.get("results") or []) if t.get("team_id") == t2_id), 0),
    #                     })
    #     except Exception as e:
    #         print(f"[ANALYTICS] API error: {e}")
    print(f"[ANALYTICS] pandascore_id={match.pandascore_id}, token={bool(token)}")
    if token and match.pandascore_id:
        try:
            r = requests.get(
                f"https://api.pandascore.co/matches/{match.pandascore_id}?token={token}",
                timeout=10
            )
            print(f"[ANALYTICS] Match API status: {r.status_code}")
            if r.status_code == 200:
                api_match = r.json()
                opponents = api_match.get("opponents") or []
                print(f"[ANALYTICS] Opponents: {len(opponents)}")
                if len(opponents) >= 2:
                    t1_id = opponents[0]["opponent"]["id"]
                    t2_id = opponents[1]["opponent"]["id"]
                    print(f"[ANALYTICS] t1_id={t1_id} t2_id={t2_id}")

                    r1 = requests.get(f"https://api.pandascore.co/teams/{t1_id}?token={token}", timeout=10)
                    print(f"[ANALYTICS] T1 players: {r1.status_code}")
                    if r1.status_code == 200:
                        t1_players = active_roster(r1.json().get("players") or [])
                        print(f"[ANALYTICS] T1 count: {len(t1_players)}")

                    r2 = requests.get(f"https://api.pandascore.co/teams/{t2_id}?token={token}", timeout=10)
                    print(f"[ANALYTICS] T2 players: {r2.status_code}")
                    if r2.status_code == 200:
                        t2_players = r2.json().get("players") or []
                        print(f"[ANALYTICS] T2 count: {len(t2_players)}")

                    r3 = requests.get(
                        f"https://api.pandascore.co/teams/{t1_id}/matches?token={token}&filter[status]=finished&per_page=5&sort=-begin_at",
                        timeout=10
                    )
                    print(f"[ANALYTICS] T1 recent: {r3.status_code}")
                    if r3.status_code == 200:
                        t1_recent = r3.json()
                        print(f"[ANALYTICS] T1 recent count: {len(t1_recent)}")

                    r4 = requests.get(
                        f"https://api.pandascore.co/teams/{t2_id}/matches?token={token}&filter[status]=finished&per_page=5&sort=-begin_at",
                        timeout=10
                    )
                    print(f"[ANALYTICS] T2 recent: {r4.status_code}")
                    if r4.status_code == 200:
                        t2_recent = r4.json()
                        print(f"[ANALYTICS] T2 recent count: {len(t2_recent)}")

                games = api_match.get("games") or []
                print(f"[ANALYTICS] Games: {len(games)}")
                for game in games:
                    if not game.get("finished"):
                        continue
                    game_id = game.get("id")
                    game_response = requests.get(
                        f"https://api.pandascore.co/csgo/games/{game_id}?token={token}",
                        timeout=10
                    )
                    print(f"[ANALYTICS] Game {game_id} API status: {game_response.status_code}")
                    if game_response.status_code != 200:
                        continue
                    game_data = game_response.json()
                    print(f"[ANALYTICS] Full game {game_id}: {game_data}")
                    map_data = game_data.get("map") or {}
                    results = game_data.get("results") or []
                    winner = game_data.get("winner") or {}
                    t1_score = next(
                        (result.get("score") for result in results if result.get("team_id") == t1_id),
                        "—"
                    )
                    t2_score = next(
                        (result.get("score") for result in results if result.get("team_id") == t2_id),
                        "—"
                    )
                    maps_data.append({
                        "map": map_data.get("name", "Map unavailable"),
                        "winner": winner.get("name", ""),
                        "t1_score": t1_score,
                        "t2_score": t2_score,
                    })
        except Exception as e:
            print(f"[ANALYTICS] ERROR: {e}")
            import traceback
            traceback.print_exc()
    user_prediction = Prediction.query.filter_by(
        user_id=current_user.id, match_id=match_id
    ).first()
    return render_template('match_analytics.html',
        match=match,
        api_match=api_match,
        t1_players=t1_players,
        t2_players=t2_players,
        t1_recent=t1_recent,
        t2_recent=t2_recent,
        maps_data=maps_data,
        user_prediction=user_prediction,
    )

@app.route('/user/<username>/history')
@login_required
def user_history(username):
    user = User.query.filter_by(username=username).first_or_404()
    t_filter = request.args.get('tournament')
    time_range = request.args.get('range')
    query = Prediction.query.filter_by(user_id=user.id).join(Match)
    if time_range == 'week':
        one_week_ago = datetime.now() - timedelta(days=7)
        query = query.filter(Match.date >= one_week_ago) 
    elif time_range == 'month':
        one_month_ago = datetime.now() - timedelta(days=30)
        query = query.filter(Match.date >= one_month_ago)
    if t_filter:
        query = query.filter(Match.tournament_name == t_filter)
    predictions = query.order_by(Match.id.desc()).all()
    all_t = db.session.query(Match.tournament_name)\
        .join(Prediction, Prediction.match_id == Match.id)\
        .filter(Prediction.user_id == user.id)\
        .distinct().all()
    tournaments = [t[0] for t in all_t if t[0]]
    return render_template('user/user_history.html', 
                           user=user, 
                           predictions=predictions, 
                           tournaments=tournaments,
                           selected_tournament=t_filter,
                           selected_range=time_range)

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self';"
    )
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

def keep_alive():
    try:
        import requests as req
        req.get("https://elitehub-2bvk.onrender.com/", timeout=10)
        print("[KEEP-ALIVE] Pinged seccessfully")
    except Exception as e:
        print(f"[KEEP-ALIVE] Failed: {e}")

# /------- PANDASCORE AUTO API ------/
def normalize_logo_url(url):
    if not url:
        return ""
    return url.strip()

def auto_fetch_pandascore_matches():
    token = os.getenv("PANDASCORE_TOKEN", "")
    if not token:
        print("[BG-TASK] Missing PANDASCORE_TOKEN")
        return
    def normalize_logo_url(url):
        if not url:
            return ""
        url = str(url).strip()
        return "https://" + url[len("http://"):] if url.startswith("http://") else url
    def format_prize_pool(raw):
        if not raw:
            return "TBD"
        if isinstance(raw, (int, float)):
            return f"${int(raw):,}"
        digits = re.sub(r"[^\d]", "", str(raw))
        return f"${int(digits):,}" if digits else str(raw).strip()
    status_mapping = {
        "finished": "Finished",
        "running": "Live",
        "not_started": "Upcoming",
        "postponed": "Upcoming",
        "canceled": "Finished",
    }
    try:
        all_matches = []
        # Upcoming
        r = requests.get(f"https://api.pandascore.co/csgo/matches/upcoming?token={token}&per_page=100", timeout=15)
        if r.status_code == 200:
            all_matches += r.json()
        # Live
        r = requests.get(f"https://api.pandascore.co/csgo/matches/running?token={token}&per_page=50", timeout=15)
        if r.status_code == 200:
            all_matches += r.json()
        # Past
        for page in range(1, 4):
            r = requests.get(f"https://api.pandascore.co/csgo/matches/past?token={token}&per_page=100&page={page}", timeout=15)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break
            all_matches += data
            print(f"[BG-TASK] Past page {page}: {len(data)} matches")

        print(f"[BG-TASK] Total fetched: {len(all_matches)}")
        with app.app_context():
            for item in all_matches:
                opponents = item.get("opponents") or []
                if len(opponents) < 2:
                    continue
                if not opponents[0].get("opponent") or not opponents[1].get("opponent"):
                    continue
                league = item.get("league") or {}
                serie = item.get("serie") or {}      # ← correct key
                league_name = (league.get("name") or "").strip()
                serie_name = (serie.get("full_name") or serie.get("name") or "").strip()
                if serie_name:
                    if league_name.lower() in serie_name.lower():
                        api_tournament_name = serie_name
                    else:
                        api_tournament_name = f"{league_name} {serie_name}"
                else:
                    api_tournament_name = league_name or "Unknown Tournament"
                league_tier = (league.get("tier") or "").lower()
                is_target = (league_tier in ["s", "a"]) or any(
                    kw in api_tournament_name.upper()
                    for kw in ["IEM", "MAJOR", "INTEL EXTREME", "ESL", "BLAST", "EPL", "EWC", "STARLADDER", "PGL"]
                )
                if not is_target:
                    continue
                tournament_logo = normalize_logo_url(
                    league.get("image_url") or serie.get("image_url") or ""
                )
                # tournament.image_url = tournament_logo
                final_prize_pool = format_prize_pool(
                    serie.get("prizepool") or serie.get("prize_pool") or
                    league.get("prizepool") or league.get("prize_pool")
                )
                existing_tournament = Tournament.query.filter(
                    Tournament.name.ilike(f"%{league_name}%")
                ).first()
                if existing_tournament:
                    final_tournament_name = existing_tournament.name
                    if tournament_logo and not existing_tournament.image_url:
                        existing_tournament.image_url = tournament_logo
                    if final_prize_pool != "TBD" and not existing_tournament.prize_pool or existing_tournament.prize_pool == "TBD":
                        existing_tournament.prize_pool = final_prize_pool
                else:
                    new_t = Tournament(
                        name=api_tournament_name,
                        prize_pool=final_prize_pool,
                        date="Ongoing",
                        xp_reward="100 XP",
                        image_url=tournament_logo,
                    )
                    db.session.add(new_t)
                    db.session.flush()
                    final_tournament_name = new_t.name
                    print(f"[BG-TASK] New tournament: {final_tournament_name}")

                begin_at = item.get("begin_at")
                if not begin_at:
                    continue
                utc_time = datetime.strptime(begin_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
                local_time = utc_time.astimezone(pytz.timezone("Europe/Berlin"))
                date_str = local_time.strftime("%B %d")
                time_str = local_time.strftime("%H:%M")

                team1_obj = opponents[0]["opponent"]
                team2_obj = opponents[1]["opponent"]
                team1_name = (team1_obj.get("name") or "TBD").strip()
                team2_name = (team2_obj.get("name") or "TBD").strip()
                team1_logo = normalize_logo_url(team1_obj.get("image_url") or "")
                team2_logo = normalize_logo_url(team2_obj.get("image_url") or "")
                match_type_str = f"BO{item.get('number_of_games', 3)}"
                current_db_status = status_mapping.get(item.get("status", "not_started"), "Upcoming")
                existing_match = Match.query.filter(
                    Match.team1.ilike(team1_name),
                    Match.team2.ilike(team2_name),
                    Match.status != "Finished"
                ).first()
                if existing_match:
                    if not existing_match.pandascore_id:
                        existing_match.pandascore_id = item.get("id")
                    existing_match.tournament_name = final_tournament_name
                    existing_match.date = date_str
                    existing_match.time = time_str
                    existing_match.match_type = match_type_str
                    if team1_logo:
                        existing_match.team1_logo = team1_logo
                    if team2_logo:
                        existing_match.team2_logo = team2_logo
                    if existing_match.status != current_db_status:
                        if current_db_status == "Finished":
                            t1_id = team1_obj.get("id")
                            t2_id = team2_obj.get("id")
                            t1_score, t2_score = 0, 0
                            for res in item.get("results", []):
                                if res.get("team_id") == t1_id:
                                    t1_score = res.get("score", 0)
                                elif res.get("team_id") == t2_id:
                                    t2_score = res.get("score", 0)
                            final_score_str = f"{t1_score}:{t2_score}"
                            existing_match.final_score = final_score_str
                            existing_match.status = "Finished"
                else:
                    already_done = Match.query.filter(
                        Match.team1.ilike(team1_name),
                        Match.team2.ilike(team2_name),
                        Match.status == "Finished"
                    ).first()
                    if not already_done:
                        db.session.add(Match(
                            tournament_name=final_tournament_name,
                            team1=team1_name,
                            team2=team2_name,
                            team1_logo=team1_logo,
                            team2_logo=team2_logo,
                            date=date_str,
                            time=time_str,
                            status=current_db_status,
                            match_type=match_type_str,
                            pandascore_id=item.get("id")
                        ))
                        print(f"[BG-TASK] Added: {team1_name} vs {team2_name} ({current_db_status})")
            db.session.commit()
            print("[BG-TASK] DATABASE UPDATED SUCCESSFULLY")
    except Exception as e:
        db.session.rollback()
        print(f"[BG-TASK] ERROR: {e}")
        import traceback
        traceback.print_exc()
scheduler = BackgroundScheduler()
scheduler.add_job(func=auto_fetch_pandascore_matches, trigger="interval", hours=12, start_date=datetime.now() + timedelta(minutes=5))
scheduler.add_job(keep_alive, 'interval', minutes=13)
if os.environ.get('WERKZEUG_RUN_MAIN') != 'false':
    try:
        scheduler.start()
        print("[SCHEDULER] Started successfully")
        if os.getenv("RUN_TELEGRAM_BOT") == "true":
            start_bot_thread()
            print("[BOT] BOT IS WORKING THREAD LAUNCHED")
        else:
            print("[BOT] DISABELD")
    except Exception as e:
        print(f"[SCHEDULER] Already running: {e}")

@app.route('/sync-api-now')
@login_required
def sync_api_now():
    if not getattr(current_user, 'is_admin', False):
        flash("Admins only!")
        return redirect(url_for('index'))
    try:
        auto_fetch_pandascore_matches()
        flash("Sync complete! Matches, logos and tournaments updated.", "success")
    except Exception as e:
        flash(f"Sync failed: {e}")
    return redirect(url_for('matches'))

@app.route('/debug-stale-matches')
@login_required
def debug_stale_matches():
    if not getattr(current_user, 'is_admin', False):
        return "Admins only", 403

    token = os.getenv("PANDASCORE_TOKEN", "")
    url_past = f"https://api.pandascore.co/csgo/matches/past?token={token}&per_page=60"
    res = requests.get(url_past, timeout=15)

    stale = Match.query.filter(Match.status != "Finished").all()
    api_matches = res.json() if res.status_code == 200 else []

    output = {
        "stale_db_matches": [
            {"id": m.id, "team1": m.team1, "team2": m.team2, "date": m.date, "time": m.time, "status": m.status, "tournament": m.tournament_name}
            for m in stale
        ],
        "api_past_count": len(api_matches),
        "api_past_sample": [
            {
                "team1": (a.get("opponents") or [{}])[0].get("opponent", {}).get("name"),
                "team2": (a.get("opponents") or [{}, {}])[1].get("opponent", {}).get("name") if len(a.get("opponents") or [])>1 else None,
                "status": a.get("status"),
                "begin_at": a.get("begin_at"),
            }
            for a in api_matches[:15]
        ]
    }
    from flask import jsonify
    return jsonify(output)

@app.route("/ping")
def test_cron():
    return "ok"

@app.route('/generate-telegram-code')
@login_required
def generate_telegram_code():
    import secrets
    code = secrets.token_hex(8)
    current_user.telegram_link_code = code
    db.session.commit()
    from flask import jsonify
    return jsonify({"code": code})

if __name__ == '__main__':
    app.run(debug=False)